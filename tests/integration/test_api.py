"""Integration tests for the FastAPI REST API (Sprint 3).

Requirements: 11.1 – 11.6

Uses ``httpx.AsyncClient`` with the ASGI transport — no running server needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest

from backend.api.main import create_app
from backend.models.article import Article
from backend.storage.storage_layer import StorageLayer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage() -> StorageLayer:
    s = StorageLayer(":memory:")
    s.init_db()
    return s


@pytest.fixture
def app(storage: StorageLayer):
    return create_app(storage=storage)


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


_TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _make_article(
    *,
    article_id: str | None = None,
    title: str = "Test Article",
    url: str | None = None,
    source: str = "test-source",
    published_at: str | None = None,
    fetched_at: str | None = None,
    category: str | None = None,
) -> Article:
    return Article(
        id=article_id or str(uuid.uuid4()),
        title=title,
        url=url or f"https://example.com/{uuid.uuid4()}",
        source=source,
        published_at=published_at or f"{_TODAY}T12:00:00Z",
        fetched_at=fetched_at or f"{_TODAY}T13:00:00Z",
        summary="A short summary.",
        authors=["Alice"],
        tags=["ai"],
        category=category,
        raw={"key": "value"},
    )


# ---------------------------------------------------------------------------
# GET /articles
# ---------------------------------------------------------------------------


class TestListArticles:
    async def test_empty_db_returns_empty_list(self, client):
        resp = await client.get("/articles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["page_size"] == 20

    async def test_returns_all_articles(self, client, storage):
        a1 = _make_article(title="First")
        a2 = _make_article(title="Second")
        storage.save_batch([a1, a2])

        resp = await client.get("/articles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_filters_by_category(self, client, storage):
        ai_article = _make_article(title="AI News", category="AI")
        ml_article = _make_article(title="ML News", category="ML")
        storage.save_batch([ai_article, ml_article])

        resp = await client.get("/articles", params={"category": "AI"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "AI News"

    async def test_filters_by_source(self, client, storage):
        src_a = _make_article(title="From A", source="source-a")
        src_b = _make_article(title="From B", source="source-b")
        storage.save_batch([src_a, src_b])

        resp = await client.get("/articles", params={"source": "source-a"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "From A"

    async def test_filters_by_date_range(self, client, storage):
        early = _make_article(
            title="Early", published_at="2024-01-15T00:00:00Z",
        )
        late = _make_article(
            title="Late", published_at="2024-02-01T00:00:00Z",
        )
        storage.save_batch([early, late])

        resp = await client.get(
            "/articles",
            params={
                "date_from": "2024-01-10T00:00:00Z",
                "date_to": "2024-01-20T00:00:00Z",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Early"

    async def test_pagination(self, client, storage):
        articles = [
            _make_article(title=f"Article {i}")
            for i in range(5)
        ]
        storage.save_batch(articles)

        resp = await client.get("/articles", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert body["page"] == 1
        assert body["page_size"] == 2

        resp2 = await client.get("/articles", params={"page": 3, "page_size": 2})
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert len(body2["items"]) == 1
        assert body2["total"] == 5

    async def test_invalid_page_size_returns_400(self, client):
        resp = await client.get("/articles", params={"page_size": 0})
        assert resp.status_code == 400

        resp2 = await client.get("/articles", params={"page_size": 101})
        assert resp2.status_code == 400

    async def test_invalid_page_returns_400(self, client):
        resp = await client.get("/articles", params={"page": 0})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /articles/{id}
# ---------------------------------------------------------------------------


class TestGetArticle:
    async def test_returns_article_by_id(self, client, storage):
        article = _make_article(
            article_id="550e8400-e29b-41d4-a716-446655440000",
        )
        storage.save_batch([article])

        resp = await client.get(
            f"/articles/{article.id}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == article.id
        assert body["title"] == article.title
        assert body["url"] == article.url
        assert body["source"] == article.source

    async def test_returns_404_for_missing_id(self, client):
        resp = await client.get(
            "/articles/550e8400-e29b-41d4-a716-446655440999",
        )
        assert resp.status_code == 404

    async def test_returns_404_for_nonexistent_uuid(self, client):
        resp = await client.get(
            f"/articles/{uuid.uuid4()}",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /trends
# ---------------------------------------------------------------------------


class TestGetTrends:
    async def test_returns_empty_when_no_articles(self, client):
        resp = await client.get("/trends")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_groups_by_category_and_date(self, client, storage):
        now = datetime.now(timezone.utc)
        day1 = now.strftime("%Y-%m-%d") + "T10:00:00Z"
        day2 = now.strftime("%Y-%m-%d") + "T10:00:00Z"

        storage.save_batch([
            _make_article(title="A", published_at=day1, category="AI"),
            _make_article(title="B", published_at=day1, category="AI"),
            _make_article(title="C", published_at=day1, category="ML"),
        ])

        resp = await client.get("/trends", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()

        assert len(data) == 2

        ai = [d for d in data if d["category"] == "AI"]
        assert len(ai) == 1
        assert ai[0]["count"] == 2

        ml = [d for d in data if d["category"] == "ML"]
        assert len(ml) == 1
        assert ml[0]["count"] == 1

    async def test_uncategorized_articles_grouped(self, client, storage):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "T10:00:00Z"
        storage.save_batch([
            _make_article(title="No cat", published_at=now, category=None),
            _make_article(title="No cat 2", published_at=now, category=None),
        ])

        resp = await client.get("/trends", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "Uncategorized"
        assert data[0]["count"] == 2

    async def test_invalid_days_returns_400(self, client):
        resp = await client.get("/trends", params={"days": 0})
        assert resp.status_code == 400

        resp2 = await client.get("/trends", params={"days": 366})
        assert resp2.status_code == 400


# ---------------------------------------------------------------------------
# GET /sources
# ---------------------------------------------------------------------------


class TestListSources:
    async def test_returns_empty_when_no_articles(self, client):
        resp = await client.get("/sources")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_distinct_sources(self, client, storage):
        storage.save_batch([
            _make_article(source="techcrunch", fetched_at="2024-01-15T10:00:00Z"),
            _make_article(source="techcrunch", fetched_at="2024-01-16T10:00:00Z"),
            _make_article(source="arxiv", fetched_at="2024-01-15T12:00:00Z"),
        ])

        resp = await client.get("/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        sources = {s["source"]: s for s in data}
        assert "techcrunch" in sources
        assert "arxiv" in sources
        assert sources["techcrunch"]["last_scraped_at"] == "2024-01-16T10:00:00Z"
        assert sources["arxiv"]["last_scraped_at"] == "2024-01-15T12:00:00Z"


# ---------------------------------------------------------------------------
# OpenAPI docs
# ---------------------------------------------------------------------------


class TestOpenApi:
    async def test_docs_returns_200(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    async def test_openapi_json_returns_200(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "AI Intelligence Dashboard API"
