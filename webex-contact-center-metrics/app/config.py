import os


class Settings:
    """Application settings loaded from environment variables."""

    app_name: str = os.getenv(
        "APP_NAME",
        "Webex Contact Center Metrics",
    )

    environment: str = os.getenv(
        "ENVIRONMENT",
        "development",
    )

    log_level: str = os.getenv(
        "LOG_LEVEL",
        "INFO",
    )

    webhook_secret: str = os.getenv(
        "WEBEX_WEBHOOK_SECRET",
        "",
    )

    database_url: str = os.getenv(
        "DATABASE_URL",
        "",
    )

    webex_client_id: str = os.getenv(
        "WEBEX_CLIENT_ID",
        "",
    )

    webex_client_secret: str = os.getenv(
        "WEBEX_CLIENT_SECRET",
        "",
    )

    webex_service_app_id: str = os.getenv(
        "WEBEX_SERVICE_APP_ID",
        "",
    )

    webex_access_token: str = os.getenv(
        "WEBEX_ACCESS_TOKEN",
        "",
    )

    webex_refresh_token: str = os.getenv(
        "WEBEX_REFRESH_TOKEN",
        "",
    )


settings = Settings()
