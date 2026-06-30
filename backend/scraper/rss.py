"""RSS/Atom feed scraper for the AI Intelligence Dashboard.

Uses ``feedparser`` for parsing. All fetch/parse errors are caught and logged;
the method always returns a (possibly empty) list — it never raises.
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx

from backend.config.config_loader import FeedConfig
from backend.scraper.base import AbstractScraper

logger = logging.getLogger(__name__)


class RSSNewsScraper(AbstractScraper):
    """Scraper for a single RSS or Atom feed.

    Parameters
    ----------
    feed_config:
        The feed configuration entry (name, url, etc.) from ``AppConfig``.
    lookback_hours:
        How many hours back to consider. Entries with a parseable
        ``published_parsed`` that falls before ``now - lookback_hours`` are
        dropped. Entries with no ``published_parsed`` are kept (the Normalizer
        will handle the missing timestamp).
    """

    def __init__(self, feed_config: FeedConfig, lookback_hours: int) -> None:
        self._feed_config = feed_config
        self._lookback_hours = lookback_hours

    # ------------------------------------------------------------------
    # AbstractScraper interface
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return self._feed_config.name

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch and parse the RSS/Atom feed.

        Returns
        -------
        list[dict[str, Any]]
            Deduplicated list of raw entry dicts, filtered to the look-back
            window. Returns ``[]`` on any fetch or parse error.
        """
        try:
            return self._fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RSS scraper failed for source %r: %s",
                self.source_name,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self) -> list[dict[str, Any]]:
        """Internal fetch — may raise; wrapped by ``fetch()``."""
        with httpx.Client(timeout=30.0) as client:
            response = client.get(self._feed_config.url)
        response.raise_for_status()

        parsed = feedparser.parse(response.text)

        if parsed.get("bozo") and not parsed.get("entries"):
            raise ValueError(
                f"Feed bozo error: {parsed.get('bozo_exception', 'unknown')}"
            )

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self._lookback_hours)

        records: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for entry in parsed.get("entries", []):
            # --- look-back window filter ---
            if not self._within_window(entry, cutoff):
                continue

            # --- field extraction ---
            url: str = getattr(entry, "link", "") or ""
            if not url:
                # Skip entries with no URL — nothing useful to store.
                continue

            # --- URL deduplication (keep first occurrence) ---
            if url in seen_urls:
                continue
            seen_urls.add(url)

            record = self._extract(entry, url)
            record["source"] = self.source_name
            records.append(record)

        return records

    # ------------------------------------------------------------------

    @staticmethod
    def _within_window(entry: Any, cutoff: datetime) -> bool:
        """Return True if the entry should be included (within the window).

        Entries with no ``published_parsed`` are always included — the
        Normalizer is responsible for handling missing timestamps.
        """
        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed is None:
            return True

        try:
            # ``published_parsed`` is a ``time.struct_time`` in UTC.
            entry_dt = datetime.fromtimestamp(
                calendar.timegm(published_parsed), tz=timezone.utc
            )
        except (TypeError, ValueError, OverflowError):
            # Malformed struct_time — include the entry and let Normalizer decide.
            return True

        return entry_dt >= cutoff

    @staticmethod
    def _extract(entry: Any, url: str) -> dict[str, Any]:
        """Extract canonical fields from a feedparser entry.

        All remaining entry attributes are preserved under the ``raw`` key so
        that no information is lost before normalization.

        Parameters
        ----------
        entry:
            A feedparser entry object.
        url:
            The already-resolved URL for this entry (``entry.link``).
        """
        title: str | None = getattr(entry, "title", None)
        published_at: str | None = getattr(entry, "published", None)
        summary: str | None = getattr(entry, "summary", None)

        # Build the ``raw`` dict from the entry's own __dict__ (feedparser
        # entries behave like dicts as well, so we use the dict interface).
        try:
            raw: dict[str, Any] = dict(entry)
        except Exception:  # noqa: BLE001
            raw = {}

        return {
            "title": title,
            "url": url,
            "published_at": published_at,
            "source": None,  # filled in by the caller / Normalizer from source_name
            "summary": summary,
            "raw": raw,
        }
