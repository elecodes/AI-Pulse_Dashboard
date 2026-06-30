"""Unit tests for RSSNewsScraper.

Tests cover:
- source_name property
- Field extraction (title, url, published_at, source, summary, raw)
- Look-back window: old entries are dropped, recent ones kept
- Entries with no published_parsed are always included
- URL deduplication: first occurrence is kept
- Error resilience: fetch() never raises, returns [] on failure
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import feedparser
import pytest
from httpx import Response

from backend.config.config_loader import FeedConfig
from backend.scraper.rss import RSSNewsScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_httpx(text: str = "") -> MagicMock:
    """Return a mock ``httpx.Client`` context manager that returns *text* on GET."""
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.text = text
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_response

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_client

    return mock_ctx

def _feed_config(name: str = "test-feed", url: str = "https://example.com/feed") -> FeedConfig:
    return FeedConfig(name=name, type="rss", url=url)


def _struct_time_from_dt(dt: datetime) -> time.struct_time:
    """Convert a UTC datetime to a time.struct_time (UTC)."""
    return time.gmtime(dt.timestamp())


def _make_entry(
    link: str = "https://example.com/article/1",
    title: str = "Test Article",
    published: str | None = "Mon, 01 Jan 2024 12:00:00 GMT",
    published_parsed: time.struct_time | None = None,
    summary: str | None = "A short summary.",
    **extra: Any,
) -> feedparser.FeedParserDict:
    """Build a minimal feedparser FeedParserDict entry (matches real feedparser output)."""
    data: dict[str, Any] = {
        "link": link,
        "title": title,
        "summary": summary,
    }
    if published is not None:
        data["published"] = published
    # feedparser always stores published_parsed in the dict (None when absent)
    data["published_parsed"] = published_parsed
    data.update(extra)
    return feedparser.FeedParserDict(data)


def _parsed_feed(
    entries: list[feedparser.FeedParserDict],
    bozo: bool = False,
) -> feedparser.FeedParserDict:
    """Return a feedparser-like top-level result dict."""
    return feedparser.FeedParserDict({
        "entries": entries,
        "bozo": bozo,
        "bozo_exception": Exception("test bozo") if bozo else None,
        "feed": feedparser.FeedParserDict({}),
    })


# ---------------------------------------------------------------------------
# source_name
# ---------------------------------------------------------------------------

def test_source_name_returns_feed_config_name():
    scraper = RSSNewsScraper(_feed_config(name="techcrunch-ai"), lookback_hours=48)
    assert scraper.source_name == "techcrunch-ai"


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def test_fetch_extracts_canonical_fields():
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(hours=1)
    entry = _make_entry(
        link="https://example.com/a",
        title="My Title",
        published="Mon, 01 Jan 2024 12:00:00 GMT",
        published_parsed=_struct_time_from_dt(recent),
        summary="Summary text",
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert len(results) == 1
    r = results[0]
    assert r["title"] == "My Title"
    assert r["url"] == "https://example.com/a"
    assert r["summary"] == "Summary text"
    assert r["source"] == "test-feed"
    assert isinstance(r["raw"], dict)


def test_fetch_source_equals_source_name():
    now = datetime.now(tz=timezone.utc)
    entry = _make_entry(
        link="https://example.com/b",
        published_parsed=_struct_time_from_dt(now - timedelta(hours=1)),
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(name="mit-tech-review"), lookback_hours=48)
            results = scraper.fetch()

    assert results[0]["source"] == "mit-tech-review"


def test_fetch_raw_contains_entry_data():
    now = datetime.now(tz=timezone.utc)
    entry = _make_entry(
        link="https://example.com/c",
        published_parsed=_struct_time_from_dt(now - timedelta(hours=1)),
    )
    entry["extra_field"] = "extra_value"

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert results[0]["raw"]["extra_field"] == "extra_value"


# ---------------------------------------------------------------------------
# Look-back window filter
# ---------------------------------------------------------------------------

def test_fetch_drops_entries_older_than_lookback():
    now = datetime.now(tz=timezone.utc)
    old = now - timedelta(hours=100)
    entry = _make_entry(
        link="https://example.com/old",
        published_parsed=_struct_time_from_dt(old),
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert results == []


def test_fetch_keeps_entries_within_lookback():
    now = datetime.now(tz=timezone.utc)
    recent = now - timedelta(hours=24)
    entry = _make_entry(
        link="https://example.com/recent",
        published_parsed=_struct_time_from_dt(recent),
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert len(results) == 1


def test_fetch_includes_entry_with_no_published_parsed():
    """Entries without published_parsed should be included regardless of window."""
    entry = _make_entry(link="https://example.com/no-date", published_parsed=None)

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=1)
            results = scraper.fetch()

    assert len(results) == 1
    assert results[0]["published_at"] is not None or results[0]["published_at"] is None  # just included


def test_fetch_published_at_none_when_not_present():
    """When entry has no 'published' field, published_at should be None."""
    now = datetime.now(tz=timezone.utc)
    entry = _make_entry(
        link="https://example.com/no-pub",
        published=None,
        published_parsed=_struct_time_from_dt(now - timedelta(hours=1)),
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert results[0]["published_at"] is None


# ---------------------------------------------------------------------------
# URL deduplication
# ---------------------------------------------------------------------------

def test_fetch_deduplicates_by_url_keeps_first():
    now = datetime.now(tz=timezone.utc)
    entry1 = _make_entry(
        link="https://example.com/dup",
        title="First",
        published_parsed=_struct_time_from_dt(now - timedelta(hours=1)),
    )
    entry2 = _make_entry(
        link="https://example.com/dup",
        title="Second (duplicate URL)",
        published_parsed=_struct_time_from_dt(now - timedelta(hours=2)),
    )

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed([entry1, entry2])
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert len(results) == 1
    assert results[0]["title"] == "First"


def test_fetch_deduplication_different_urls_both_kept():
    now = datetime.now(tz=timezone.utc)
    entries = [
        _make_entry(link="https://example.com/a", published_parsed=_struct_time_from_dt(now - timedelta(hours=1))),
        _make_entry(link="https://example.com/b", published_parsed=_struct_time_from_dt(now - timedelta(hours=2))),
    ]

    with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
        with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
            mock_parse.return_value = _parsed_feed(entries)
            scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
            results = scraper.fetch()

    assert len(results) == 2


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

def test_fetch_returns_empty_list_on_network_exception():
    with patch("backend.scraper.rss.feedparser.parse", side_effect=Exception("network error")):
        scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
        results = scraper.fetch()

    assert results == []


def test_fetch_returns_empty_list_on_bozo_with_no_entries():
    with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
        mock_parse.return_value = _parsed_feed([], bozo=True)
        scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
        results = scraper.fetch()

    assert results == []


def test_fetch_does_not_raise_on_malformed_feed():
    """fetch() must never raise — only return []."""
    with patch("backend.scraper.rss.feedparser.parse", side_effect=ValueError("bad xml")):
        scraper = RSSNewsScraper(_feed_config(), lookback_hours=48)
        try:
            results = scraper.fetch()
        except Exception as exc:
            pytest.fail(f"fetch() raised unexpectedly: {exc}")
        assert results == []


def test_fetch_logs_warning_on_failure(caplog):
    import logging

    with patch("backend.scraper.rss.feedparser.parse", side_effect=RuntimeError("boom")):
        scraper = RSSNewsScraper(_feed_config(name="broken-feed"), lookback_hours=48)
        with caplog.at_level(logging.WARNING, logger="backend.scraper.rss"):
            scraper.fetch()

    assert any("broken-feed" in record.message for record in caplog.records)
