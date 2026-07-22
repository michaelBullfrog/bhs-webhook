import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/webex/contact-center",
    tags=["Webex Contact Center"],
)


@router.get("/webhook")
async def webhook_status() -> dict[str, str]:
    """Browser-friendly readiness check for the webhook route."""
    return {
        "status": "ready",
        "message": "Webex Contact Center webhook endpoint is available",
    }


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def receive_webex_webhook(request: Request) -> JSONResponse:
    """Receive and log Webex Contact Center webhook events."""
    try:
        payload: dict[str, Any] = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must contain valid JSON",
        ) from exc

    received_at = datetime.now(timezone.utc)

    event_type = (
        payload.get("eventType")
        or payload.get("event")
        or payload.get("type")
        or "unknown"
    )

    logger.info(
        "Webex Contact Center event received | "
        "event_type=%s | received_at=%s | payload=%s",
        event_type,
        received_at.isoformat(),
        json.dumps(payload, default=str),
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "accepted": True,
            "eventType": event_type,
            "receivedAt": received_at.isoformat(),
        },
    )
