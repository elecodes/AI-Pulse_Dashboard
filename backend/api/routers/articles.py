"""Article listing and detail endpoints for the AI Intelligence Dashboard API.

Requirements: 11.1, 11.2
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.dependencies import get_storage
from backend.models.article import Article
from backend.storage.storage_layer import StorageLayer

router = APIRouter(tags=["articles"])


@router.get("/articles")
async def list_articles(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = None,
    source: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    storage: StorageLayer = Depends(get_storage),
) -> dict[str, Any]:
    """Return a paginated list of articles with optional filters."""
    offset = (page - 1) * page_size

    articles = storage.get_articles(
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        q=q,
        limit=page_size,
        offset=offset,
    )
    total = storage.count_articles(
        date_from=date_from,
        date_to=date_to,
        category=category,
        source=source,
        q=q,
    )

    return {
        "items": articles,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/articles/{article_id}")
async def get_article(
    article_id: str,
    storage: StorageLayer = Depends(get_storage),
) -> Article:
    """Return a single article by its UUID.

    Raises ``404`` when the article does not exist.
    """
    article = storage.get_article_by_id(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
