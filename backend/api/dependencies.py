"""FastAPI dependencies for the AI Intelligence Dashboard API."""

from __future__ import annotations

from fastapi import Request

from backend.storage.storage_layer import StorageLayer


def get_storage(request: Request) -> StorageLayer:
    """Return the StorageLayer instance stored in the application state."""
    return request.app.state.storage
