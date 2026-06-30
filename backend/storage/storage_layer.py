"""Storage layer for the AI Intelligence Dashboard.

Wraps SQLAlchemy Core (not ORM) with a SQLite backend. All writes are
transactional and roll back on any exception. JSON snapshot exports are
written atomically via a tmp-file-then-rename strategy.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.models.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL (executed verbatim — matches design.md exactly)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL UNIQUE,
    source       TEXT NOT NULL,
    published_at TEXT,
    fetched_at   TEXT NOT NULL,
    summary      TEXT,
    authors      TEXT NOT NULL DEFAULT '[]',
    tags         TEXT NOT NULL DEFAULT '[]',
    category     TEXT,
    classification_failed INTEGER NOT NULL DEFAULT 0,
    raw          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles (source);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category);

CREATE TABLE IF NOT EXISTS runs (
    id                 TEXT PRIMARY KEY,
    started_at         TEXT NOT NULL,
    ended_at           TEXT,
    articles_fetched   INTEGER NOT NULL DEFAULT 0,
    articles_inserted  INTEGER NOT NULL DEFAULT 0,
    articles_deduped   INTEGER NOT NULL DEFAULT 0,
    articles_discarded INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);
"""

_FTS_SCHEMA_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title,
    summary,
    content='articles',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
"""


class StorageLayer:
    """Persistent store for Articles and pipeline run records.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file.  Pass ``":memory:"`` for
        an in-memory database (useful in tests).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._engine: Engine | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_engine(self) -> Engine:
        """Return (creating if necessary) the SQLAlchemy engine."""
        if self._engine is None:
            raise RuntimeError(
                "StorageLayer not initialised — call init_db() first."
            )
        return self._engine

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ------------------------------------------------------------------
    # Task 11.1 — schema initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create the DB file (and parent directories) then apply the schema.

        Operation is idempotent: ``CREATE TABLE IF NOT EXISTS`` / ``CREATE
        INDEX IF NOT EXISTS`` mean repeated calls are safe.

        Requirements: 6.1, 6.7
        """
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        connect_url = (
            "sqlite:///:memory:"
            if self._db_path == ":memory:"
            else f"sqlite:///{self._db_path}"
        )
        self._engine = create_engine(connect_url, echo=False)

        with self._engine.begin() as conn:
            # Execute each non-empty statement separately; SQLAlchemy's
            # text() does not support multiple statements in one call on
            # all drivers.
            for statement in _SCHEMA_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(text(stmt))

            # Sprint 2: add classification_failed column to existing DBs
            try:
                conn.execute(
                    text(
                        "ALTER TABLE articles ADD COLUMN "
                        "classification_failed INTEGER NOT NULL DEFAULT 0"
                    )
                )
            except Exception:
                pass  # Column already exists or was just created

            # Sprint 5: FTS5 full-text search virtual table
            for fts_stmt in _FTS_SCHEMA_SQL.strip().split(";"):
                stmt = fts_stmt.strip()
                if stmt:
                    conn.execute(text(stmt))

        logger.info("Database initialised at %r", self._db_path)

    # ------------------------------------------------------------------
    # Task 11.2 — batch upsert
    # ------------------------------------------------------------------

    def save_batch(self, articles: list[Article]) -> tuple[int, int]:
        """Persist a list of Articles, upserting on URL uniqueness.

        On conflict (same URL), only ``fetched_at`` and ``raw`` are updated;
        all other fields retain the original values.

        Parameters
        ----------
        articles:
            Articles produced by the Normalizer.

        Returns
        -------
        tuple[int, int]
            ``(inserted_count, deduped_count)`` where *deduped_count* is the
            number of articles whose URL was already present.

        Raises
        ------
        Exception
            Any database exception is re-raised after rolling back the
            transaction.

        Requirements: 6.3, 6.8
        """
        if not articles:
            return 0, 0

        engine = self._get_engine()
        inserted_count = 0
        deduped_count = 0

        upsert_sql = text(
            """
            INSERT INTO articles
    (id, title, url, source, published_at, fetched_at, summary,
     authors, tags, category, classification_failed, raw)
VALUES
    (:id, :title, :url, :source, :published_at, :fetched_at,
     :summary, :authors, :tags, :category, :classification_failed, :raw)
            ON CONFLICT(url) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                raw        = excluded.raw
            """
        )

        # We need to know whether each row was an insert or an update.
        # SQLite's changes() returns 1 for both INSERT and UPDATE in an
        # upsert, but last_insert_rowid() changes only on a true insert.
        # The most reliable approach: check existence before the upsert.
        exists_sql = text("SELECT 1 FROM articles WHERE url = :url")

        with engine.begin() as conn:
            try:
                for article in articles:
                    already_exists = conn.execute(
                        exists_sql, {"url": article.url}
                    ).fetchone() is not None

                    conn.execute(
                        upsert_sql,
                        {
                            "id": article.id,
                            "title": article.title,
                            "url": article.url,
                            "source": article.source,
                            "published_at": article.published_at,
                            "fetched_at": article.fetched_at,
                            "summary": article.summary,
                            "authors": json.dumps(article.authors),
                            "tags": json.dumps(article.tags),
                            "category": article.category,
                            "classification_failed": int(article.classification_failed),
                            "raw": json.dumps(article.raw),
                        },
                    )

                    if already_exists:
                        deduped_count += 1
                    else:
                        inserted_count += 1

                conn.execute(text("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')"))

            except Exception:
                logger.error(
                    "save_batch failed — transaction rolled back.", exc_info=True
                )
                raise

        logger.info(
            "save_batch: inserted=%d deduped=%d", inserted_count, deduped_count
        )
        return inserted_count, deduped_count

    # ------------------------------------------------------------------
    # Task 11.6 — update classifications (Sprint 2)
    # ------------------------------------------------------------------

    def update_articles_classification(self, articles: list[Article]) -> None:
        """Update classification fields for articles matching by URL.

        Sets ``category``, ``summary``, and ``classification_failed`` for
        each article whose URL already exists in the database.

        Parameters
        ----------
        articles:
            Articles with classification results.  Only fields relevant to
            classification are updated; all other columns are preserved.
        """
        engine = self._get_engine()
        update_sql = text(
            """
            UPDATE articles SET
                category = :category,
                summary = :summary,
                classification_failed = :classification_failed
            WHERE url = :url
            """
        )
        with engine.begin() as conn:
            for article in articles:
                conn.execute(
                    update_sql,
                    {
                        "url": article.url,
                        "category": article.category,
                        "summary": article.summary,
                        "classification_failed": int(article.classification_failed),
                    },
                )

    # ------------------------------------------------------------------
    # Task 11.3 — query
    # ------------------------------------------------------------------

    def _search_fts(self, q: str) -> list[str]:
        if not q or not q.strip():
            return []

        engine = self._get_engine()

        terms = [f'"{w.replace("\"", "")}"' for w in q.split() if w.strip()]
        if not terms:
            return []

        safe_query = " OR ".join(terms)

        sql = text(
            "SELECT id FROM articles "
            "WHERE rowid IN ("
            "  SELECT rowid FROM articles_fts WHERE articles_fts MATCH :q"
            ")"
        )
        with engine.connect() as conn:
            rows = conn.execute(sql, {"q": safe_query}).mappings().all()

        return [row["id"] for row in rows]

    @staticmethod
    def _build_article_where(
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        source: str | None = None,
        matching_ids: list[str] | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Build WHERE conditions and params for article queries."""
        conditions: list[str] = []
        params: dict[str, Any] = {}

        if date_from is not None:
            conditions.append("published_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            conditions.append("published_at <= :date_to")
            params["date_to"] = date_to
        if category is not None:
            conditions.append("category = :category")
            params["category"] = category
        if source is not None:
            conditions.append("source = :source")
            params["source"] = source
        if matching_ids is not None:
            placeholders = ", ".join(f":mid_{i}" for i in range(len(matching_ids)))
            conditions.append(f"id IN ({placeholders})")
            for i, mid in enumerate(matching_ids):
                params[f"mid_{i}"] = mid

        return conditions, params

    def get_articles(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Article]:
        """Return Articles, optionally filtered.

        Parameters
        ----------
        date_from:
            Inclusive lower bound ISO 8601 string (UTC).  ``None`` means no
            lower bound.
        date_to:
            Inclusive upper bound ISO 8601 string (UTC).  ``None`` means no
            upper bound.
        category:
            Filter by exact category match.  ``None`` means no filter.
        source:
            Filter by source name.  ``None`` means no filter.
        q:
            Full-text search query against title and summary via FTS5.
        limit:
            Maximum number of rows to return.  ``None`` means unlimited.
        offset:
            Number of rows to skip.  ``None`` means no offset.

        Returns
        -------
        list[Article]
            Ordered by ``published_at`` DESC (NULLs last by SQLite default).

        Requirements: 6.4, 6.5, 11.1
        """
        engine = self._get_engine()

        matching_ids = None
        if q:
            matching_ids = self._search_fts(q)
            if not matching_ids:
                return []

        conditions, params = self._build_article_where(
            date_from, date_to, category, source, matching_ids,
        )

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query_str = f"SELECT * FROM articles {where_clause} ORDER BY published_at DESC"

        if limit is not None:
            query_str += " LIMIT :limit"
            params["limit"] = limit
        if offset is not None:
            query_str += " OFFSET :offset"
            params["offset"] = offset

        query = text(query_str)

        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        return [self._row_to_article(row) for row in rows]

    def count_articles(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        category: str | None = None,
        source: str | None = None,
        q: str | None = None,
    ) -> int:
        """Return the total number of articles matching the given filters.

        Parameters
        ----------
        Same as :meth:`get_articles` (without pagination params).

        Returns
        -------
        int
            Total matching row count.

        Requirements: 11.1
        """
        engine = self._get_engine()

        matching_ids = None
        if q:
            matching_ids = self._search_fts(q)
            if not matching_ids:
                return 0

        conditions, params = self._build_article_where(
            date_from, date_to, category, source, matching_ids,
        )

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = text(f"SELECT count(*) as cnt FROM articles {where_clause}")

        with engine.connect() as conn:
            row = conn.execute(query, params).mappings().one()

        return row["cnt"]

    # ------------------------------------------------------------------
    # Task 11.7 — single article lookup (Sprint 3)
    # ------------------------------------------------------------------

    def get_article_by_id(self, article_id: str) -> Article | None:
        """Return a single Article by its UUID, or ``None`` if not found.

        Requirements: 11.2
        """
        engine = self._get_engine()
        query = text("SELECT * FROM articles WHERE id = :id")

        with engine.connect() as conn:
            row = conn.execute(query, {"id": article_id}).mappings().first()

        return self._row_to_article(row) if row else None

    # ------------------------------------------------------------------
    # Task 11.8 — sources list (Sprint 3)
    # ------------------------------------------------------------------

    def get_sources(self) -> list[dict[str, Any]]:
        """Return distinct sources with their latest fetch timestamp.

        Returns
        -------
        list[dict]
            Each dict has keys ``source`` (str) and ``last_scraped_at``
            (str ISO 8601 or ``None``).  Ordered by source name.

        Requirements: 11.4
        """
        engine = self._get_engine()
        query = text(
            "SELECT source, MAX(fetched_at) as last_scraped_at "
            "FROM articles GROUP BY source ORDER BY source"
        )

        with engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        return [
            {"source": row["source"], "last_scraped_at": row["last_scraped_at"]}
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Task 11.9 — trends (Sprint 3)
    # ------------------------------------------------------------------

    def get_trends(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return article volume per category per day.

        Articles with a ``NULL`` category are grouped under
        ``"Uncategorized"``.  Results are sorted by date descending, then
        category ascending.

        Parameters
        ----------
        date_from:
            Inclusive lower bound.  ``None`` means no lower bound.
        date_to:
            Inclusive upper bound.  ``None`` means no upper bound.

        Returns
        -------
        list[dict]
            Each dict has keys ``category`` (str | None),
            ``date`` (str), ``count`` (int).

        Requirements: 11.3
        """
        engine = self._get_engine()

        conditions: list[str] = []
        params: dict[str, Any] = {}

        if date_from is not None:
            conditions.append("published_at >= :date_from")
            params["date_from"] = date_from
        if date_to is not None:
            conditions.append("published_at <= :date_to")
            params["date_to"] = date_to

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        query = text(
            f"SELECT "
            f"  COALESCE(category, 'Uncategorized') as category, "
            f"  DATE(published_at) as date, "
            f"  COUNT(*) as count "
            f"FROM articles "
            f"{where_clause} "
            f"GROUP BY category, DATE(published_at) "
            f"ORDER BY date DESC, category ASC"
        )

        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        return [
            {
                "category": row["category"],
                "date": row["date"],
                "count": row["count"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Task 11.4 — JSON export
    # ------------------------------------------------------------------

    def export_json(self, path: str) -> None:
        """Write all articles to *path* as a JSON array (atomic swap).

        Writes to ``<path>.tmp`` first, then ``os.replace()`` for an atomic
        rename.  Parent directories are created as needed.

        Requirements: 6.2
        """
        articles = self.get_articles()

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp_path = f"{path}.tmp"

        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(
                [json.loads(article.to_json()) for article in articles],
                fh,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(tmp_path, path)
        logger.info("Exported %d articles to %r", len(articles), path)

    # ------------------------------------------------------------------
    # Task 11.5 — run tracking
    # ------------------------------------------------------------------

    def begin_run(self) -> str:
        """Insert a new run record with status='running'.

        Returns
        -------
        str
            The UUID v4 run identifier.

        Requirements: 6.6
        """
        engine = self._get_engine()
        run_id = str(uuid.uuid4())
        started_at = self._utc_now_iso()

        insert_sql = text(
            """
            INSERT INTO runs (id, started_at, status)
            VALUES (:id, :started_at, :status)
            """
        )

        with engine.begin() as conn:
            conn.execute(
                insert_sql,
                {"id": run_id, "started_at": started_at, "status": "running"},
            )

        logger.info("Run %r started at %s", run_id, started_at)
        return run_id

    def end_run(self, run_id: str, stats: dict[str, Any]) -> None:
        """Update a run record with final counts and status.

        Parameters
        ----------
        run_id:
            Identifier returned by :meth:`begin_run`.
        stats:
            Dict with keys: ``fetched``, ``inserted``, ``deduped``,
            ``discarded``, ``status``.

        Requirements: 6.6
        """
        engine = self._get_engine()
        ended_at = self._utc_now_iso()

        update_sql = text(
            """
            UPDATE runs SET
                ended_at           = :ended_at,
                articles_fetched   = :fetched,
                articles_inserted  = :inserted,
                articles_deduped   = :deduped,
                articles_discarded = :discarded,
                status             = :status
            WHERE id = :id
            """
        )

        with engine.begin() as conn:
            conn.execute(
                update_sql,
                {
                    "ended_at": ended_at,
                    "fetched": stats.get("fetched", 0),
                    "inserted": stats.get("inserted", 0),
                    "deduped": stats.get("deduped", 0),
                    "discarded": stats.get("discarded", 0),
                    "status": stats.get("status", "success"),
                    "id": run_id,
                },
            )

        logger.info(
            "Run %r ended — status=%r stats=%r", run_id, stats.get("status"), stats
        )

    # ------------------------------------------------------------------
    # Private — row deserialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_article(row: Any) -> Article:
        """Convert a SQLAlchemy RowMapping to an Article."""
        return Article(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            source=row["source"],
            published_at=row["published_at"],
            fetched_at=row["fetched_at"],
            summary=row["summary"],
            authors=json.loads(row["authors"]),
            tags=json.loads(row["tags"]),
            category=row["category"],
            classification_failed=bool(row.get("classification_failed", 0)),
            raw=json.loads(row["raw"]),
        )
