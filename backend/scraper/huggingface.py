"""Hugging Face model feed scraper for the AI Intelligence Dashboard.

Fetches from the Hugging Face public REST API (``https://huggingface.co/api/models``).
Uses ``httpx`` with a configurable timeout. Falls back to the fetch timestamp as
``published_at`` when the API response contains no native date field. All errors are
caught and logged; ``fetch()`` never raises.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.config.config_loader import FeedConfig
from backend.scraper.base import AbstractScraper

logger = logging.getLogger(__name__)

_HF_BASE_URL = "https://huggingface.co"


class HuggingFaceScraper(AbstractScraper):
    """Scraper for the Hugging Face public model API.

    Fetches a list of model objects from the configured endpoint, extracts
    canonical fields, deduplicates by URL (first occurrence wins), and falls
    back to the current UTC timestamp when no native publication date is present.

    Parameters
    ----------
    feed_config:
        Feed configuration entry (must have ``type == "huggingface"``) with a
        ``url`` pointing to the API endpoint (default:
        ``https://huggingface.co/api/models``).
    lookback_hours:
        Retained for interface consistency with other scrapers. The HF API does
        not always provide useful date metadata, so look-back filtering is
        applied only when a native date is present on the item.
    timeout:
        HTTP request timeout in seconds (default: 30.0).
    """

    def __init__(
        self,
        feed_config: FeedConfig,
        lookback_hours: int,
        timeout: float = 30.0,
    ) -> None:
        self._feed_config = feed_config
        self._lookback_hours = lookback_hours
        self._timeout = timeout

    # ------------------------------------------------------------------
    # AbstractScraper interface
    # ------------------------------------------------------------------

    @property
    def source_name(self) -> str:
        return self._feed_config.name

    def fetch(self) -> list[dict[str, Any]]:
        """Fetch models from the Hugging Face API.

        Returns
        -------
        list[dict[str, Any]]
            Deduplicated list of raw model dicts. Returns ``[]`` on any
            error — never raises.
        """
        try:
            return self._fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "HuggingFace scraper failed for source %r: %s",
                self.source_name,
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self) -> list[dict[str, Any]]:
        """Internal implementation — may raise; wrapped by ``fetch()``."""
        # Capture the fetch time before the HTTP call so it can be used as the
        # fallback ``published_at`` for any item that lacks a native date.
        fetch_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(self._feed_config.url)

        if response.status_code != 200:
            logger.warning(
                "HuggingFace API returned HTTP %d for source %r",
                response.status_code,
                self.source_name,
            )
            return []

        items: list[Any] = response.json()

        if not isinstance(items, list):
            logger.warning(
                "HuggingFace API response is not a list for source %r; "
                "got %s",
                self.source_name,
                type(items).__name__,
            )
            return []

        records: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                continue

            record = self._extract(item, fetch_ts)

            url: str = record["url"]
            if not url:
                continue

            # Deduplicate by URL — keep first occurrence.
            if url in seen_urls:
                continue
            seen_urls.add(url)

            records.append(record)

        return records

    def _extract(self, item: dict[str, Any], fetch_ts: str) -> dict[str, Any]:
        """Extract canonical fields from a single HF API model object.

        Parameters
        ----------
        item:
            Raw dict from the HF API response.
        fetch_ts:
            UTC ISO 8601 timestamp captured at the start of the fetch; used
            as the ``published_at`` fallback when the item has no native date.
        """
        model_id: str = item.get("modelId", item.get("id", "")) or ""
        title: str = model_id  # model ID doubles as the display name

        url: str = f"{_HF_BASE_URL}/{model_id}" if model_id else ""

        summary: str | None = item.get("description") or None

        # Prefer lastModified → createdAt → fallback to fetch timestamp.
        published_at: str | None = (
            item.get("lastModified")
            or item.get("createdAt")
            or fetch_ts
        )

        return {
            "title": title,
            "url": url,
            "summary": summary,
            "published_at": published_at,
            "source": self.source_name,
            "raw": item,
        }
