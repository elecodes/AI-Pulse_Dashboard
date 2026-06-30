"""Pipeline orchestrator for the AI Intelligence Dashboard.

Coordinates the full scrape → normalize → store sequence as a single
atomic run.  Enforces a configurable timeout and records run metadata
in the ``runs`` table.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Timer
from typing import Any

from backend.classifier.base import AbstractClassifier
from backend.classifier.rule import RuleClassifier
from backend.config.config_loader import AppConfig, FeedConfig
from backend.normalizer.normalizer import Normalizer
from backend.scraper.arxiv import ArXivScraper
from backend.scraper.base import AbstractScraper
from backend.scraper.huggingface import HuggingFaceScraper
from backend.scraper.rss import RSSNewsScraper
from backend.storage.storage_layer import StorageLayer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Stats returned by a single pipeline run."""

    run_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    duration_seconds: float = 0.0
    feeds_configured: int = 0
    feeds_succeeded: int = 0
    feeds_failed: int = 0
    raw_records_fetched: int = 0
    articles_inserted: int = 0
    articles_deduped: int = 0
    articles_discarded: int = 0
    status: str = "success"  # 'success' | 'failure' | 'timeout'
    error: str | None = None


# ---------------------------------------------------------------------------
# Scraper registry
# ---------------------------------------------------------------------------


def _build_scraper(feed: FeedConfig, lookback_hours: int) -> AbstractScraper:
    """Return a scraper instance matching *feed.type*.

    Parameters
    ----------
    feed:
        Feed configuration.
    lookback_hours:
        Look-back window in hours passed from ``AppConfig``.

    Raises
    ------
    ValueError
        If ``feed.type`` is not a recognised scraper type.
    """
    scraper_map: dict[str, type[AbstractScraper]] = {
        "rss": RSSNewsScraper,
        "arxiv": ArXivScraper,
        "huggingface": HuggingFaceScraper,
    }
    cls = scraper_map.get(feed.type)
    if cls is None:
        raise ValueError(
            f"Unknown feed type {feed.type!r} for feed {feed.name!r}. "
            f"Supported types: {list(scraper_map)}"
        )
    return cls(feed, lookback_hours=lookback_hours)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """Orchestrates a single scrape → normalise → store run.

    Parameters
    ----------
    config:
        Fully validated ``AppConfig`` instance.
    storage:
        Initialised ``StorageLayer`` instance (``init_db()`` must have been
        called before the first ``run()`` call).
    """

    def __init__(
        self,
        config: AppConfig,
        storage: StorageLayer,
        classifier: AbstractClassifier | None = None,
    ) -> None:
        self._config = config
        self._storage = storage
        self._classifier = classifier or RuleClassifier()
        self._normalizer = Normalizer()
        self._scrapers: list[AbstractScraper] = [
            _build_scraper(feed, config.lookback_hours)
            for feed in config.feeds if feed.enabled
        ]
        self._timeout_timer: Timer | None = None
        self._timed_out = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, dry_run: bool = False) -> RunResult:
        """Execute the full pipeline: scrape → normalise → store.

        Parameters
        ----------
        dry_run:
            When ``True``, all scraping and normalisation steps are executed
            but no data is written to the storage layer.

        Returns
        -------
        RunResult
            Aggregated statistics for the run.
        """
        result = RunResult()
        result.feeds_configured = len(self._scrapers)
        result.started_at = self._utc_now_iso()

        logger.info(
            "Pipeline run starting — %d feed(s) configured: %s",
            result.feeds_configured,
            [s.source_name for s in self._scrapers],
        )

        # --- begin run tracking -------------------------------------------
        try:
            result.run_id = self._storage.begin_run()
        except Exception as exc:
            logger.error("Failed to begin run record: %s", exc, exc_info=True)
            result.status = "failure"
            result.error = str(exc)
            result.ended_at = self._utc_now_iso()
            return result

        # --- start timeout timer ------------------------------------------
        timeout = self._config.pipeline_timeout_seconds
        self._start_timeout(timeout, result.run_id)

        # --- scrape -------------------------------------------------------
        all_raw: list[dict[str, Any]] = []

        try:
            for scraper in self._scrapers:
                if self._timed_out:
                    break
                try:
                    records = scraper.fetch()
                    all_raw.extend(records)
                    result.feeds_succeeded += 1
                    logger.debug(
                        "Feed %r returned %d record(s)",
                        scraper.source_name,
                        len(records),
                    )
                except Exception as exc:
                    result.feeds_failed += 1
                    logger.warning(
                        "Feed %r failed: %s", scraper.source_name, exc
                    )
        except Exception as exc:
            # Catastrophic failure during scraping loop
            logger.error("Scraping loop failed: %s", exc, exc_info=True)
            self._cancel_timeout()
            self._finalise_run(result, status="failure", error=str(exc))
            return result

        result.raw_records_fetched = len(all_raw)

        # --- normalise ----------------------------------------------------
        if not self._timed_out:
            try:
                articles, discard_count = self._normalizer.normalize_all(all_raw)
                result.articles_discarded = discard_count
            except Exception as exc:
                logger.error("Normalisation failed: %s", exc, exc_info=True)
                self._cancel_timeout()
                self._finalise_run(result, status="failure", error=str(exc))
                return result
        else:
            articles = []

        # --- store --------------------------------------------------------
        if not self._timed_out and not dry_run:
            try:
                inserted, deduped = self._storage.save_batch(articles)
                result.articles_inserted = inserted
                result.articles_deduped = deduped

                self._storage.export_json(self._config.json_export_path)
            except Exception as exc:
                logger.error("Storage write failed: %s", exc, exc_info=True)
                self._cancel_timeout()
                self._finalise_run(result, status="failure", error=str(exc))
                return result

        # --- classify (Sprint 2) ------------------------------------------
        if not self._timed_out and not dry_run and self._classifier is not None and articles:
            try:
                classified = self._classifier.classify_batch(articles)
                self._storage.update_articles_classification(classified)
                self._storage.export_json(self._config.json_export_path)
            except Exception as exc:
                logger.warning("Article classification failed — pipeline continues: %s", exc)

        # --- finalise -----------------------------------------------------
        self._cancel_timeout()

        if self._timed_out:
            self._finalise_run(result, status="timeout")
        else:
            self._finalise_run(result, status="success")

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_timeout(self, timeout: int, run_id: str) -> None:
        """Start a background timer that marks the run as timed out."""

        def _on_timeout() -> None:
            self._timed_out = True
            logger.error(
                "Pipeline run %r timed out after %d seconds", run_id, timeout
            )

        self._timeout_timer = Timer(timeout, _on_timeout)
        self._timeout_timer.daemon = True
        self._timeout_timer.start()

    def _cancel_timeout(self) -> None:
        """Cancel the timeout timer if it is still running."""
        if self._timeout_timer is not None:
            self._timeout_timer.cancel()
            self._timeout_timer = None

    def _finalise_run(
        self,
        result: RunResult,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update the run record in storage and populate result fields."""
        result.status = status
        result.error = error
        result.ended_at = self._utc_now_iso()

        start = datetime.fromisoformat(result.started_at)
        end = datetime.fromisoformat(result.ended_at)
        result.duration_seconds = (end - start).total_seconds()

        try:
            self._storage.end_run(
                result.run_id,
                {
                    "fetched": result.raw_records_fetched,
                    "inserted": result.articles_inserted,
                    "deduped": result.articles_deduped,
                    "discarded": result.articles_discarded,
                    "status": status,
                },
            )
        except Exception as exc:
            logger.error("Failed to finalise run record: %s", exc, exc_info=True)

        logger.info(
            "Pipeline run %r finished — status=%s "
            "fetched=%d inserted=%d deduped=%d discarded=%d "
            "duration=%.2fs",
            result.run_id,
            status,
            result.raw_records_fetched,
            result.articles_inserted,
            result.articles_deduped,
            result.articles_discarded,
            result.duration_seconds,
        )

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
