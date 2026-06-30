"""Unit tests for backend.storage.storage_layer (Tasks 11.1–11.5 + 11.9).

Covers:
- DB file auto-creation on first init_db() call
- init_db() idempotency (calling twice does not fail)
- Run record written to runs table after pipeline completes
"""
import json
import os
import tempfile

import pytest

from sqlalchemy import text

from backend.models.article import Article
from backend.storage.storage_layer import StorageLayer


@pytest.fixture
def storage() -> StorageLayer:
    s = StorageLayer(":memory:")
    s.init_db()
    return s


@pytest.fixture
def sample_article() -> Article:
    return Article(
        id="550e8400-e29b-41d4-a716-446655440000",
        title="Test Article",
        url="https://example.com/article",
        source="test-source",
        published_at="2024-01-15T12:00:00Z",
        fetched_at="2024-01-15T13:00:00Z",
        summary="A short summary.",
        authors=["Alice"],
        tags=["ai"],
        category=None,
        raw={"key": "value"},
    )


class TestInitDb:
    def test_auto_creates_db_file(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            os.unlink(db_path)
            assert not os.path.exists(db_path)
            s = StorageLayer(db_path)
            s.init_db()
            assert os.path.exists(db_path), "init_db() must create the DB file"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_init_db_is_idempotent(self, storage):
        storage.init_db()
        storage.init_db()

    def test_tables_exist_after_init(self, storage):
        engine = storage._get_engine()
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            ).fetchall()
        table_names = [row[0] for row in tables]
        assert "articles" in table_names
        assert "runs" in table_names


class TestSaveBatch:
    def test_insert_and_dedup_counts(self, storage, sample_article):
        a2 = Article(
            id="660e8400-e29b-41d4-a716-446655440001",
            title="Second Article",
            url="https://example.com/second",
            source="test-source",
            published_at="2024-01-15T14:00:00Z",
            fetched_at="2024-01-15T15:00:00Z",
            summary="Second summary.",
            authors=["Bob"],
            tags=["ml"],
            category=None,
            raw={"key": "value2"},
        )
        inserted, deduped = storage.save_batch([sample_article, a2])
        assert inserted == 2
        assert deduped == 0

    def test_dedup_on_duplicate_url(self, storage, sample_article):
        storage.save_batch([sample_article])
        updated = Article(
            id="660e8400-e29b-41d4-a716-446655440001",
            title="Updated Title",
            url="https://example.com/article",
            source="test-source",
            published_at="2024-01-15T12:00:00Z",
            fetched_at="2024-01-15T14:00:00Z",
            summary="Updated summary.",
            authors=["Alice", "Bob"],
            tags=["ai", "ml"],
            category="research",
            raw={"key": "updated"},
        )
        inserted, deduped = storage.save_batch([updated])
        assert inserted == 0
        assert deduped == 1

    def test_upsert_updates_only_fetched_at_and_raw(self, storage, sample_article):
        storage.save_batch([sample_article])
        updated = Article(
            id="660e8400-e29b-41d4-a716-446655440001",
            title="Updated Title",
            url="https://example.com/article",
            source="test-source",
            published_at="2024-01-15T12:00:00Z",
            fetched_at="2024-01-15T14:00:00Z",
            summary="Updated summary.",
            authors=["Alice", "Bob"],
            tags=["ai", "ml"],
            category="research",
            raw={"key": "updated"},
        )
        storage.save_batch([updated])
        articles = storage.get_articles()
        assert len(articles) == 1
        saved = articles[0]
        # updated fields
        assert saved.fetched_at == "2024-01-15T14:00:00Z"
        assert saved.raw == {"key": "updated"}
        # original fields preserved
        assert saved.title == "Test Article"
        assert saved.summary == "A short summary."
        assert saved.authors == ["Alice"]
        assert saved.tags == ["ai"]
        assert saved.category is None

    def test_empty_batch(self, storage):
        inserted, deduped = storage.save_batch([])
        assert inserted == 0
        assert deduped == 0


class TestGetArticles:
    def test_returns_empty_when_no_articles(self, storage):
        assert storage.get_articles() == []

    def test_returns_all_without_date_filter(self, storage, sample_article):
        storage.save_batch([sample_article])
        articles = storage.get_articles()
        assert len(articles) == 1
        assert articles[0].id == sample_article.id

    def test_filters_by_date_range(self, storage):
        early = Article(
            id="1", title="Early", url="https://example.com/1",
            source="test", published_at="2024-01-01T00:00:00Z",
            fetched_at="2024-01-01T01:00:00Z", summary=None,
        )
        middle = Article(
            id="2", title="Middle", url="https://example.com/2",
            source="test", published_at="2024-01-15T00:00:00Z",
            fetched_at="2024-01-15T01:00:00Z", summary=None,
        )
        late = Article(
            id="3", title="Late", url="https://example.com/3",
            source="test", published_at="2024-02-01T00:00:00Z",
            fetched_at="2024-02-01T01:00:00Z", summary=None,
        )
        storage.save_batch([early, middle, late])
        result = storage.get_articles(
            date_from="2024-01-10T00:00:00Z",
            date_to="2024-01-20T00:00:00Z",
        )
        assert len(result) == 1
        assert result[0].title == "Middle"

    def test_orders_by_published_at_desc(self, storage):
        early = Article(
            id="1", title="A", url="https://example.com/a",
            source="test", published_at="2024-01-01T00:00:00Z",
            fetched_at="2024-01-01T01:00:00Z", summary=None,
        )
        late = Article(
            id="2", title="B", url="https://example.com/b",
            source="test", published_at="2024-02-01T00:00:00Z",
            fetched_at="2024-02-01T01:00:00Z", summary=None,
        )
        storage.save_batch([early, late])
        articles = storage.get_articles()
        assert articles[0].title == "B"
        assert articles[1].title == "A"


class TestExportJson:
    def test_export_creates_file_with_articles(self, storage, sample_article):
        storage.save_batch([sample_article])
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            export_path = f.name
        try:
            os.unlink(export_path)
            storage.export_json(export_path)
            assert os.path.exists(export_path)
            with open(export_path, "r") as fh:
                data = json.load(fh)
            assert len(data) == 1
            assert data[0]["title"] == "Test Article"
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)

    def test_export_empty_creates_empty_array(self, storage):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            export_path = f.name
        try:
            os.unlink(export_path)
            storage.export_json(export_path)
            with open(export_path, "r") as fh:
                data = json.load(fh)
            assert data == []
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)


class TestRunTracking:
    def test_begin_run_returns_valid_run_id(self, storage):
        run_id = storage.begin_run()
        assert isinstance(run_id, str)
        assert len(run_id) > 0

    def test_end_run_updates_status(self, storage):
        run_id = storage.begin_run()
        storage.end_run(run_id, {"status": "success"})
        engine = storage._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status FROM runs WHERE id = :rid"),
                {"rid": run_id},
            ).fetchone()
        assert row is not None
        assert row[0] == "success"
