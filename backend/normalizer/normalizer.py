"""Normalizer for the AI Intelligence Dashboard.

Transforms raw source dicts into canonical Article instances.
Validates required fields, normalizes timestamps to UTC ISO 8601,
truncates summaries at the 2000-byte UTF-8 boundary, and generates
stable UUIDs and fetched_at timestamps.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from backend.models.article import Article

logger = logging.getLogger(__name__)

# Fields that must be present and non-empty in the raw record.
_REQUIRED_FIELDS: tuple[str, ...] = ("title", "url", "published_at")

# Maximum byte length for the summary field.
_SUMMARY_MAX_BYTES: int = 2000


class Normalizer:
    """Stateless normalizer: raw dict → Article | None."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, raw: dict[str, Any]) -> Article | None:
        """Normalize a single raw record into an Article.

        Parameters
        ----------
        raw:
            Source-specific raw record dict.

        Returns
        -------
        Article
            Fully populated canonical Article on success.
        None
            When any required field (title, url, published_at) is absent
            or empty.  A WARNING is logged in that case.
        """
        missing = self._missing_required_fields(raw)
        if missing:
            logger.warning(
                "Discarding record — missing required fields: %s. Record source: %r",
                missing,
                raw.get("source", "<unknown>"),
            )
            return None

        published_at = self._parse_timestamp(raw["published_at"])
        fetched_at = self._utc_now_iso()

        summary_raw = raw.get("summary")
        summary = (
            self.truncate_summary(summary_raw)
            if isinstance(summary_raw, str)
            else None
        )

        authors = raw.get("authors", [])
        if not isinstance(authors, list):
            authors = []
        authors = [str(a) for a in authors]

        tags = raw.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        return Article(
            id=str(uuid.uuid4()),
            title=str(raw["title"]),
            url=str(raw["url"]),
            source=str(raw.get("source", "")),
            published_at=published_at,
            fetched_at=fetched_at,
            summary=summary,
            authors=authors,
            tags=tags,
            category=raw.get("category", None),
            raw=raw,
        )

    def normalize_all(
        self, records: list[dict[str, Any]]
    ) -> tuple[list[Article], int]:
        """Normalize a batch of raw records.

        Parameters
        ----------
        records:
            List of raw source dicts.

        Returns
        -------
        tuple[list[Article], int]
            ``(articles, discard_count)`` where *discard_count* is the
            number of records for which :meth:`normalize` returned ``None``.
        """
        articles: list[Article] = []
        discard_count: int = 0

        for record in records:
            result = self.normalize(record)
            if result is None:
                discard_count += 1
            else:
                articles.append(result)

        return articles, discard_count

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def truncate_summary(s: str) -> str:
        """Truncate *s* to at most 2000 UTF-8 bytes, preserving boundaries.

        Encodes to UTF-8, slices at 2000 bytes, then decodes with
        ``errors='ignore'`` so no partial multi-byte sequence survives.

        Parameters
        ----------
        s:
            Input string.

        Returns
        -------
        str
            Original string if its UTF-8 encoding fits within 2000 bytes,
            otherwise a truncated string of at most 2000 characters whose
            UTF-8 encoding is valid and ≤ 2000 bytes.
        """
        encoded = s.encode("utf-8")
        if len(encoded) <= _SUMMARY_MAX_BYTES:
            return s
        truncated_bytes = encoded[:_SUMMARY_MAX_BYTES]
        return truncated_bytes.decode("utf-8", errors="ignore")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _missing_required_fields(raw: dict[str, Any]) -> list[str]:
        """Return a list of required field names that are absent or empty."""
        missing: list[str] = []
        for field in _REQUIRED_FIELDS:
            value = raw.get(field)
            if value is None or value == "":
                missing.append(field)
        return missing

    @staticmethod
    def _parse_timestamp(value: Any) -> str | None:
        """Parse *value* to a UTC ISO 8601 string ``YYYY-MM-DDTHH:MM:SSZ``.

        Returns ``None`` and logs a WARNING when the value cannot be parsed.
        """
        try:
            dt = dateutil_parser.parse(str(value))
            # Convert to UTC, stripping microseconds.
            dt_utc = dt.astimezone(timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ParserError, ValueError, OverflowError, TypeError) as exc:
            logger.warning("Could not parse timestamp %r: %s", value, exc)
            return None

    @staticmethod
    def _utc_now_iso() -> str:
        """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
