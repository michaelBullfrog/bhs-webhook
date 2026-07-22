from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/webex/contact-center",
    tags=["Webex Contact Center"],
)

# Stores the 100 most recent webhook events in memory.
# These events clear whenever Render restarts or redeploys.
recent_events: deque[dict[str, Any]] = deque(maxlen=100)


@router.get("/webhook")
async def webhook_status() -> dict[str, str]:
    return {
        "status": "ready",
        "message": "Webex Contact Center webhook endpoint is available",
    }


@router.get("/events")
async def get_recent_events() -> dict[str, Any]:
    return {
        "count": len(recent_events),
        "events": list(reversed(recent_events)),
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

    event_record = {
        "eventType": event_type,
        "receivedAt": received_at.isoformat(),
        "payload": payload,
    }

    recent_events.append(event_record)

    print(event_record, flush=True)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "accepted": True,
            "eventType": event_type,
            "receivedAt": received_at.isoformat(),
        },
    )
