import logging
import os
from typing import Any

import httpx

from .database import upsert_auxiliary_codes

logger = logging.getLogger(__name__)


def get_required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


async def fetch_auxiliary_codes(
    work_type: str,
) -> list[dict[str, Any]]:
    base_url = os.getenv(
        "WEBEX_CC_API_BASE_URL",
        "https://api.wxcc-us1.cisco.com",
    ).rstrip("/")
    org_id = get_required_environment("WEBEX_ORG_ID")
    token = get_required_environment("WEBEX_ACCESS_TOKEN")

    page = 0
    page_size = 100
    all_codes: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            url = (
                f"{base_url}/organization/{org_id}"
                "/v2/auxiliary-code"
            )

            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                params={
                    "filter": (
                        f"active==true;workTypeCode=={work_type}"
                    ),
                    "attributes": (
                        "id,isSystemCode,name,defaultCode,active"
                    ),
                    "page": page,
                    "pageSize": page_size,
                    "sort": "name,asc",
                },
            )
            response.raise_for_status()
            payload = response.json()

            rows = payload.get("data") or []
            all_codes.extend(rows)

            meta = payload.get("meta") or {}
            total_pages = int(meta.get("totalPages") or 1)

            if page + 1 >= total_pages:
                break

            page += 1

    return all_codes


async def sync_auxiliary_codes() -> dict[str, int]:
    idle_codes = await fetch_auxiliary_codes("IDLE_CODE")
    wrapup_codes = await fetch_auxiliary_codes("WRAP_UP_CODE")

    idle_count = upsert_auxiliary_codes(
        idle_codes,
        "IDLE_CODE",
    )
    wrapup_count = upsert_auxiliary_codes(
        wrapup_codes,
        "WRAP_UP_CODE",
    )

    logger.info(
        "Auxiliary-code sync complete | idle=%s | wrapup=%s",
        idle_count,
        wrapup_count,
    )

    return {
        "idleCodes": idle_count,
        "wrapupCodes": wrapup_count,
        "total": idle_count + wrapup_count,
    }
