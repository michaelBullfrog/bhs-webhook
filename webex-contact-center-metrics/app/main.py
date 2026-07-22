import logging

from fastapi import FastAPI

from .config import settings
from .webhook_routes import router as webhook_router


logging.basicConfig(
    level=settings.log_level.upper(),
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description=(
        "Receives Webex Contact Center events and prepares "
        "agent metrics for PostgreSQL and Power BI."
    ),
    version="0.1.0",
)

app.include_router(webhook_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "status": "online",
        "service": settings.app_name,
        "environment": settings.environment,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event() -> None:
    logger.info(
        "Starting %s in %s mode",
        settings.app_name,
        settings.environment,
    )
