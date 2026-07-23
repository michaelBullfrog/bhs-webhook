import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import initialize_database
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
        "Receives Webex Contact Center events and stores "
        "agent metrics in PostgreSQL for real-time reporting."
    ),
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://michaelbullfrog.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
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
    initialize_database()
