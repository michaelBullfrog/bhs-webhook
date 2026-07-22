from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

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

    print(
        {
            "event_type": event_type,
            "received_at": received_at.isoformat(),
            "payload": payload,
        }
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "accepted": True,
            "eventType": event_type,
            "receivedAt": received_at.isoformat(),
        },
    )
