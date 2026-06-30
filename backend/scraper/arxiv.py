"""arXiv paper scraper for the AI Intelligence Dashboard.

Uses ``httpx`` (synchronous) to query the arXiv Atom API and ``feedparser``
to parse the Atom response. Retries up to three times with exponential
back-off via ``tenacity``. All errors are caught and logged; ``fetch()``
never raises.
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import httpx
from tenacity import (
    RetryError,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from backend.config.config_loader import FeedConfig
from backend.scraper.base import AbstractScraper

logger = logging.getLogger(__name__)

# arXiv Atom entry ID looks like "http://arxiv.org/abs/2401.12345v1"
# We keep only the bare paper ID (e.g. "2401.12345").
_ABS_PREFIX = "http://arxiv.org/abs/"


def _extract_paper_id(entry_id: str) -> str:
    """Return the bare arXiv paper ID from an entry id URL.

    Strips the ``http://arxiv.org/abs/`` prefix and any version suffix
    (``vN``), so ``http://arxiv.org/abs/2401.12345v2`` → ``2401.12345``.
    """
    bare = entry_id.strip()
    if bare.startswith(_ABS_PREFIX):
        bare = bare[len(_ABS_PREFIX):]
    # Strip version suffix if present (e.g. "2401.12345v2" → "2401.12345")
    if "v" in bare:
        bare = bare.rsplit("v", 1)[0]
    return bare


class ArXivScraper(AbstractScraper):
    """Scraper for the arXiv Atom API.

    Queries one endpoint per category listed in ``feed_config.categories``,
    merges the results, deduplicates by arXiv paper ID, and applies the
    configured look-back window.

    Parameters
    ----------
    feed_config:
        Feed configuration entry (must have ``type == "arxiv"``) with a
        ``url`` pointing to ``http://export.arxiv.org/api/query`` and a
        non-empty ``categories`` list.
    lookback_hours:
        Drop papers whose ``published_parsed`` is older than this many hours
        before the fetch time. Papers with no parseable date are kept.
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
        """Fetch papers from every configured arXiv category.

        Returns
        -------
        list[dict[str, Any]]
            Deduplicated, look-back-filtered list of raw paper dicts.
            Always returns ``[]`` on any error — never raises.
        """
        try:
            return self._fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "arXiv scraper failed for source %r: %s",
                self.source_name,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self) -> list[dict[str, Any]]:
        """Internal implementation — may raise; wrapped by ``fetch()``."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self._lookback_hours)

        records: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for category in self._feed_config.categories:
            category_records = self._fetch_category(category, cutoff)
            for record in category_records:
                paper_id: str = record["paper_id"]
                if paper_id in seen_ids:
                    continue
                seen_ids.add(paper_id)
                records.append(record)

        return records

    def _fetch_category(
        self, category: str, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Fetch and parse a single arXiv category; returns filtered records.

        The HTTP call is wrapped with tenacity retry logic. On final failure
        a warning is logged and an empty list is returned so the outer loop
        continues with the next category.
        """
        try:
            response_text = self._get_with_retry(category)
        except RetryError as exc:
            logger.warning(
                "arXiv API request failed after retries for category %r "
                "(source %r): %s",
                category,
                self.source_name,
                exc,
            )
            return []

        parsed = feedparser.parse(response_text)
        records: list[dict[str, Any]] = []

        for entry in parsed.get("entries", []):
            if not self._within_window(entry, cutoff):
                continue
            record = self._extract(entry)
            records.append(record)

        return records

    def _get_with_retry(self, category: str) -> str:
        """Perform the HTTP GET with tenacity retry; return response text.

        Tenacity is applied via a nested function so the ``@retry`` decorator
        sees a fresh callable rather than being attached to the instance —
        this avoids state leaking between calls.
        """
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=False,
        )
        def _do_get() -> str:
            url = (
                f"{self._feed_config.url}"
                f"?search_query=cat:{category}"
                f"&start=0&max_results=100"
                f"&sortBy=submittedDate&sortOrder=descending"
            )
            with httpx.Client() as client:
                response = client.get(url)

            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"arXiv returned HTTP {response.status_code} for "
                    f"category {category!r}",
                    request=response.request,
                    response=response,
                )
            return response.text

        return _do_get()  # type: ignore[return-value]

    # ------------------------------------------------------------------

    @staticmethod
    def _within_window(entry: Any, cutoff: datetime) -> bool:
        """Return True if the entry falls within the look-back window.

        Entries with no ``published_parsed`` are always included.
        """
        published_parsed = getattr(entry, "published_parsed", None)
        if published_parsed is None:
            return True

        try:
            entry_dt = datetime.fromtimestamp(
                calendar.timegm(published_parsed), tz=timezone.utc
            )
        except (TypeError, ValueError, OverflowError):
            return True

        return entry_dt >= cutoff

    @staticmethod
    def _extract(entry: Any) -> dict[str, Any]:
        """Extract canonical fields from a feedparser arXiv entry."""
        entry_id: str = getattr(entry, "id", "") or ""
        paper_id: str = _extract_paper_id(entry_id)

        title: str | None = getattr(entry, "title", None)
        # feedparser stores authors as a list of dicts: [{"name": "..."}, ...]
        raw_authors = getattr(entry, "authors", []) or []
        authors: list[str] = [
            a.get("name", "") for a in raw_authors if isinstance(a, dict)
        ]

        summary: str | None = getattr(entry, "summary", None)
        published_at: str | None = getattr(entry, "published", None)

        # PDF URL: prefer a link where type == 'application/pdf'
        links = getattr(entry, "links", []) or []
        pdf_url: str | None = None
        for link in links:
            if isinstance(link, dict) and link.get("type") == "application/pdf":
                pdf_url = link.get("href")
                break
        if pdf_url is None:
            pdf_url = getattr(entry, "link", None)

        try:
            raw: dict[str, Any] = dict(entry)
        except Exception:  # noqa: BLE001
            raw = {}

        return {
            "paper_id": paper_id,
            "title": title,
            "authors": authors,
            "summary": summary,
            "published_at": published_at,
            "url": pdf_url,
            "source": None,  # filled in downstream from source_name if needed
            "raw": raw,
        }
