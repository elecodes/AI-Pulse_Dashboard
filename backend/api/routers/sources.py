"""Sources endpoint for the AI Intelligence Dashboard API.

Requirements: 11.4
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_storage
from backend.storage.storage_layer import StorageLayer

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources(
    storage: StorageLayer = Depends(get_storage),
) -> list[dict[str, Any]]:
    """Return distinct article sources with their latest scrape timestamp."""
    return storage.get_sources()
