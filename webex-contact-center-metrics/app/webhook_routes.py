import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from .database import (
    list_current_agent_states,
    list_recent_events,
    save_webhook_event,
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
