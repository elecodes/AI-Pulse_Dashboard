"""Trends endpoint for the AI Intelligence Dashboard API.

Requirements: 11.3
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_storage
from backend.storage.storage_layer import StorageLayer

router = APIRouter(tags=["trends"])


@router.get("/trends")
async def get_trends(
    days: int = Query(default=7, ge=1, le=365),
    storage: StorageLayer = Depends(get_storage),
) -> list[dict[str, Any]]:
    """Return article volume per category per day for the last *days* days."""
    now = datetime.now(tz=timezone.utc)
    date_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_from = datetime.fromordinal(
        now.toordinal() - days + 1
    ).strftime("%Y-%m-%dT00:00:00Z")

    return storage.get_trends(date_from=date_from, date_to=date_to)
