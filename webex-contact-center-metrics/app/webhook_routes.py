import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .database import (
    get_lookup_counts,
    list_auxiliary_codes,
    list_current_agent_states,
    list_recent_events,
    save_webhook_event,
)
from .webex_lookups import (
    sync_agent_states,
    sync_all_lookups,
    sync_auxiliary_codes,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/webex/contact-center",
    tags=["Webex Contact Center"],
)


@router.get("/webhook")
async def webhook_status() -> dict[str, str]:
    return {
        "status": "ready",
        "message": "Webex Contact Center webhook endpoint is available",
    }


@router.get("/events")
async def get_recent_events(
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    try:
        events = list_recent_events(limit)
    except Exception as exc:
        logger.exception("Could not load webhook events")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {
        "count": len(events),
        "events": events,
    }


@router.get("/agents/current")
async def get_current_agents() -> dict[str, Any]:
    try:
        agents = list_current_agent_states()
    except Exception as exc:
        logger.exception("Could not load current agent states")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {
        "count": len(agents),
        "agents": agents,
    }


@router.post("/states/sync")
async def manually_sync_agent_states(
    minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description=(
            "Number of recent minutes to reconcile. "
            "Maximum is 1440 minutes."
        ),
    ),
) -> dict[str, Any]:
    try:
        result = await sync_agent_states(minutes=minutes)
    except httpx.HTTPStatusError as exc:
        logger.exception(
            "Webex Agent Activities API returned an error"
        )

        try:
            detail: Any = exc.response.json()
        except ValueError:
            detail = exc.response.text

        raise HTTPException(
            status_code=exc.response.status_code,
            detail=detail,
        ) from exc
    except Exception as exc:
        logger.exception(
            "Could not manually synchronize agent states"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "synced": True,
        "syncedAt": datetime.now(timezone.utc).isoformat(),
        **result,
    }


@router.get("/lookups/auxiliary-codes")
async def get_auxiliary_codes(
    code_type: str | None = Query(
        default=None,
        description="Optional: IDLE_CODE or WRAP_UP_CODE",
    ),
) -> dict[str, Any]:
    normalized_type = code_type.upper() if code_type else None

    if normalized_type not in {None, "IDLE_CODE", "WRAP_UP_CODE"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_type must be IDLE_CODE or WRAP_UP_CODE",
        )

    codes = list_auxiliary_codes(normalized_type)

    return {
        "count": len(codes),
        "codes": codes,
    }


@router.post("/lookups/auxiliary-codes/sync")
async def sync_auxiliary_code_lookups() -> dict[str, Any]:
    try:
        result = await sync_auxiliary_codes()
    except httpx.HTTPStatusError as exc:
        logger.exception("Webex auxiliary-code API returned an error")
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        ) from exc
    except Exception as exc:
        logger.exception("Could not synchronize auxiliary codes")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "synced": True,
        **result,
    }


@router.get("/lookups/status")
async def get_lookup_status() -> dict[str, Any]:
    return {
        "ready": True,
        **get_lookup_counts(),
    }


@router.post("/lookups/sync-all")
async def sync_all_configuration_lookups() -> dict[str, Any]:
    try:
        result = await sync_all_lookups()
    except httpx.HTTPStatusError as exc:
        logger.exception("Webex configuration API returned an error")
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text,
        ) from exc
    except Exception as exc:
        logger.exception("Could not synchronize configuration lookups")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return {
        "synced": True,
        **result,
    }


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webex_webhook(
    payload: dict[str, Any],
) -> JSONResponse:
    received_at = datetime.now(timezone.utc)

    event_type = (
        payload.get("eventType")
        or payload.get("event")
        or payload.get("type")
        or "unknown"
    )

    try:
        inserted = save_webhook_event(payload, received_at)
    except ValueError as exc:
        logger.warning("Rejected webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Could not save Webex webhook event")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save webhook event",
        ) from exc

    logger.info(
        "Stored Webex event | event_type=%s | event_id=%s | inserted=%s",
        event_type,
        payload.get("id"),
        inserted,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "accepted": True,
            "inserted": inserted,
            "eventType": event_type,
            "eventId": payload.get("id"),
            "receivedAt": received_at.isoformat(),
        },
    )
