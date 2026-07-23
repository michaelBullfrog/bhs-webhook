import logging
import os
from typing import Any

import httpx

from .database import (
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
