import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .database import (
    save_webhook_event,
    upsert_auxiliary_codes,
    upsert_contact_center_queues,
    upsert_contact_center_teams,
    upsert_contact_center_users,
)

logger = logging.getLogger(__name__)


def get_required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def api_settings() -> tuple[str, str, str]:
    return (
        os.getenv(
            "WEBEX_CC_API_BASE_URL",
            "https://api.wxcc-us1.cisco.com",
        ).rstrip("/"),
        get_required_environment("WEBEX_ORG_ID"),
        get_required_environment("WEBEX_ACCESS_TOKEN"),
    )


async def fetch_collection(
    resource: str,
    *,
    extra_params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    base_url, org_id, token = api_settings()
    page = 0
    page_size = 100
    rows: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(
                f"{base_url}/organization/{org_id}/v2/{resource}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                params={
                    "page": page,
                    "pageSize": page_size,
                    **(extra_params or {}),
                },
            )
            response.raise_for_status()
            payload = response.json()

            page_rows = payload.get("data") or []
            rows.extend(page_rows)

            meta = payload.get("meta") or {}
            total_pages = int(
                meta.get("totalPages")
                or payload.get("totalPages")
                or 1
            )
            if page + 1 >= total_pages:
                break
            page += 1

    return rows


async def fetch_auxiliary_codes(
    work_type: str,
) -> list[dict[str, Any]]:
    return await fetch_collection(
        "auxiliary-code",
        extra_params={
            "filter": f"active==true;workTypeCode=={work_type}",
            "attributes": "id,isSystemCode,name,defaultCode,active",
            "sort": "name,asc",
        },
    )


async def sync_auxiliary_codes() -> dict[str, int]:
    idle_codes = await fetch_auxiliary_codes("IDLE_CODE")
    wrapup_codes = await fetch_auxiliary_codes("WRAP_UP_CODE")

    idle_count = upsert_auxiliary_codes(idle_codes, "IDLE_CODE")
    wrapup_count = upsert_auxiliary_codes(
        wrapup_codes,
        "WRAP_UP_CODE",
    )

    return {
        "idleCodes": idle_count,
        "wrapupCodes": wrapup_count,
        "auxiliaryCodes": idle_count + wrapup_count,
    }


async def sync_directory_lookups() -> dict[str, int]:
    users = await fetch_collection("user")
    teams = await fetch_collection("team")
    queues = await fetch_collection("contact-service-queue")

    user_count = upsert_contact_center_users(users)
    team_count = upsert_contact_center_teams(teams)
    queue_count = upsert_contact_center_queues(queues)

    logger.info(
        "Directory lookup sync complete | users=%s teams=%s queues=%s",
        user_count,
        team_count,
        queue_count,
    )

    return {
        "users": user_count,
        "teams": team_count,
        "queues": queue_count,
    }


async def sync_all_lookups() -> dict[str, int]:
    directory = await sync_directory_lookups()
    auxiliary = await sync_auxiliary_codes()
    result = {**directory, **auxiliary}
    result["total"] = sum(
        value
        for key, value in result.items()
        if key != "auxiliaryCodes"
    )
    return result


def _first_value(
    source: dict[str, Any],
    *names: str,
) -> Any:
    for name in names:
        value = source.get(name)
        if value is not None and value != "":
            return value
    return None


def _timestamp_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        timestamp = int(value)
        if timestamp < 10_000_000_000:
            timestamp *= 1000
        return timestamp

    text = str(value).strip()
    if text.isdigit():
        return _timestamp_ms(int(text))

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    return int(parsed.timestamp() * 1000)


def _activity_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            row
            for row in payload
            if isinstance(row, dict)
        ]

    if not isinstance(payload, dict):
        return []

    for key in (
        "data",
        "agentActivities",
        "activities",
        "items",
        "records",
        "results",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            return [
                row
                for row in value
                if isinstance(row, dict)
            ]

        if isinstance(value, dict):
            nested_rows = _activity_rows(value)
            if nested_rows:
                return nested_rows

    return []


def _normalize_activity_state(
    activity: dict[str, Any],
) -> str | None:
    state = _first_value(
        activity,
        "currentState",
        "state",
        "agentState",
        "subStatus",
        "activityState",
    )

    if state is None:
        return None

    normalized = str(state).strip()
    aliases = {
        "wrap_up": "wrapup",
        "wrap-up": "wrapup",
        "wrap up": "wrapup",
        "not responding": "not-responding",
        "not_responding": "not-responding",
    }

    return aliases.get(normalized.lower(), normalized)


async def fetch_agent_activities(
    *,
    minutes: int = 60,
) -> list[dict[str, Any]]:
    """
    Retrieve recent Agent Activity records from Webex Contact Center.

    Endpoint:
        GET /v1/agents/activities

    Required query parameters:
        orgId
        from

    The requested from/to range is kept within the one-day API limit.
    """
    base_url, org_id, token = api_settings()
    safe_minutes = max(5, min(minutes, 1440))

    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=safe_minutes)

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.get(
            f"{base_url}/v1/agents/activities",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params={
                "orgId": org_id,
                "from": int(start.timestamp() * 1000),
                "to": int(now.timestamp() * 1000),
            },
        )
        response.raise_for_status()
        return _activity_rows(response.json())


async def sync_agent_states(
    *,
    minutes: int = 60,
) -> dict[str, Any]:
    activities = await fetch_agent_activities(minutes=minutes)

    latest: dict[
        tuple[str, str],
        tuple[int, dict[str, Any]],
    ] = {}
    skipped = 0

    for activity in activities:
        agent_id = _first_value(
            activity,
            "agentId",
            "agent_id",
        )
        channel_type = _first_value(
            activity,
            "channelType",
            "channel_type",
            "mediaType",
        ) or "telephony"
        state = _normalize_activity_state(activity)
        created_time = _timestamp_ms(
            _first_value(
                activity,
                "createdTime",
                "startTime",
                "stateStartTime",
                "eventTime",
                "timestamp",
            )
        )

        if not agent_id or not state or not created_time:
            skipped += 1
            continue

        key = (
            str(agent_id),
            str(channel_type).lower(),
        )
        existing = latest.get(key)

        if existing is None or created_time > existing[0]:
            latest[key] = (created_time, activity)

    received_at = datetime.now(timezone.utc)
    _, org_id, _ = api_settings()

    inserted = 0
    reconciled = 0

    for (
        agent_id,
        channel_type,
    ), (
        created_time,
        activity,
    ) in latest.items():
        state = _normalize_activity_state(activity)

        fingerprint_source = "|".join(
            [
                agent_id,
                channel_type,
                str(created_time),
                str(state),
                str(
                    _first_value(
                        activity,
                        "taskId",
                        "interactionId",
                        "contactId",
                    )
                    or ""
                ),
            ]
        )
        fingerprint = hashlib.sha256(
            fingerprint_source.encode("utf-8")
        ).hexdigest()[:32]

        payload = {
            "id": f"reconcile-{fingerprint}",
            "type": "agent:channel_state_change",
            "eventType": "agent:channel_state_change",
            "source": "/manual-agent-state-reconciliation",
            "comciscoorgid": org_id,
            "data": {
                "agentId": agent_id,
                "agentCiUserId": _first_value(
                    activity,
                    "agentCiUserId",
                    "ciUserId",
                ),
                "taskId": _first_value(
                    activity,
                    "taskId",
                    "interactionId",
                    "contactId",
                ),
                "queueId": _first_value(
                    activity,
                    "queueId",
                    "virtualTeamId",
                ),
                "teamId": _first_value(
                    activity,
                    "teamId",
                ),
                "channelId": _first_value(
                    activity,
                    "channelId",
                    "agentChannelId",
                ),
                "channelType": channel_type,
                "currentState": state,
                "idleCodeId": _first_value(
                    activity,
                    "idleCodeId",
                    "auxCodeId",
                ),
                "idleCodeName": _first_value(
                    activity,
                    "idleCodeName",
                    "auxCodeName",
                    "stateChangeReason",
                ),
                "wrapUpAuxCodeId": _first_value(
                    activity,
                    "wrapUpAuxCodeId",
                    "wrapupAuxCodeId",
                    "wrapUpCodeId",
                    "wrapupCodeId",
                ),
                "wrapUpCodeName": _first_value(
                    activity,
                    "wrapUpCodeName",
                    "wrapupCodeName",
                    "wrapUpReason",
                ),
                "origin": _first_value(
                    activity,
                    "origin",
                    "ani",
                ),
                "destination": _first_value(
                    activity,
                    "destination",
                    "dn",
                    "dnis",
                ),
                "createdTime": created_time,
            },
        }

        was_inserted = save_webhook_event(
            payload,
            received_at,
        )
        if was_inserted:
            inserted += 1

        reconciled += 1

    logger.info(
        (
            "Agent-state reconciliation complete | "
            "activities=%s latest=%s inserted=%s skipped=%s"
        ),
        len(activities),
        reconciled,
        inserted,
        skipped,
    )

    return {
        "activitiesRetrieved": len(activities),
        "statesReconciled": reconciled,
        "eventsInserted": inserted,
        "skipped": skipped,
        "windowMinutes": max(5, min(minutes, 1440)),
    }
