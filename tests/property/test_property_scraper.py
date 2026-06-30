"""Property-based tests for scrapers (Properties 1, 2, 3).

# Feature: ai-intel-dashboard, Property 1: Scraper look-back window filter
# Feature: ai-intel-dashboard, Property 2: Scraper resilience
# Feature: ai-intel-dashboard, Property 3: Scraper output deduplication
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import feedparser
from hypothesis import assume, given, settings, strategies as st
from httpx import Response

from backend.config.config_loader import FeedConfig
from backend.scraper.rss import RSSNewsScraper


def _mock_httpx(text: str = "") -> MagicMock:
    """Return a mock ``httpx.Client`` context manager."""
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 200
    mock_response.text = text
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get.return_value = mock_response
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_client
    return mock_ctx


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# A strategy for generating URLs
_url_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1, max_size=50,
).map(lambda s: f"https://example.com/{s}")


# A strategy for generating struct_time timestamps (UTC)
def _struct_time_from_dt(dt: datetime) -> time.struct_time:
    return time.gmtime(dt.timestamp())


# ---------------------------------------------------------------------------
# Property 1: Scraper look-back window filter
# ---------------------------------------------------------------------------

@st.composite
def entry_within_window(draw) -> feedparser.FeedParserDict:
    """Generate a feed entry with a timestamp within a random look-back window."""
    lookback = draw(st.integers(min_value=1, max_value=168))
    now = datetime.now(tz=timezone.utc)
    hours_ago = draw(st.integers(min_value=0, max_value=lookback - 1))
    published_dt = now - timedelta(hours=hours_ago)
    url = draw(_url_strategy)
    entry = feedparser.FeedParserDict({
        "link": url,
        "title": draw(st.text(max_size=50)),
        "published": published_dt.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "published_parsed": _struct_time_from_dt(published_dt),
        "summary": draw(st.text(max_size=200)),
    })
    return lookback, entry


@st.composite
def entry_outside_window(draw) -> tuple[int, feedparser.FeedParserDict]:
    """Generate a feed entry with a timestamp outside the look-back window."""
    lookback = draw(st.integers(min_value=1, max_value=168))
    now = datetime.now(tz=timezone.utc)
    hours_ago = draw(st.integers(min_value=lookback + 1, max_value=lookback + 720))
    published_dt = now - timedelta(hours=hours_ago)
    url = draw(_url_strategy)
    entry = feedparser.FeedParserDict({
        "link": url,
        "title": draw(st.text(max_size=50)),
        "published": published_dt.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "published_parsed": _struct_time_from_dt(published_dt),
        "summary": draw(st.text(max_size=200)),
    })
    return lookback, entry


class TestProperty1LookBackFilter:
    # Feature: ai-intel-dashboard, Property 1: Scraper look-back window filter
    @given(entry=entry_within_window())
    @settings(max_examples=100)
    def test_entries_within_window_are_included(self, entry):
        lookback, feed_entry = entry
        config = FeedConfig(name="test-p1", type="rss", url="https://example.com/feed")
        with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
            with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
                mock_parse.return_value = feedparser.FeedParserDict({
                    "entries": [feed_entry],
                    "bozo": False,
                    "bozo_exception": None,
                    "feed": feedparser.FeedParserDict({}),
                })
                scraper = RSSNewsScraper(config, lookback_hours=lookback)
                results = scraper.fetch()
        assert len(results) == 1, f"Entry within {lookback}h window should be included"

    # Feature: ai-intel-dashboard, Property 1: Scraper look-back window filter
    @given(entry=entry_outside_window())
    @settings(max_examples=100)
    def test_entries_outside_window_are_excluded(self, entry):
        lookback, feed_entry = entry
        config = FeedConfig(name="test-p1", type="rss", url="https://example.com/feed")
        with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
            with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
                mock_parse.return_value = feedparser.FeedParserDict({
                    "entries": [feed_entry],
                    "bozo": False,
                    "bozo_exception": None,
                    "feed": feedparser.FeedParserDict({}),
                })
                scraper = RSSNewsScraper(config, lookback_hours=lookback)
                results = scraper.fetch()
        assert len(results) == 0, f"Entry {lookback}+h old should be excluded"


# ---------------------------------------------------------------------------
# Property 2: Scraper resilience — failed source does not halt pipeline
# ---------------------------------------------------------------------------

class TestProperty2Resilience:
    # Feature: ai-intel-dashboard, Property 2: Scraper resilience — failed source does not halt pipeline
    @given(
        error_type=st.sampled_from([
            ConnectionError, TimeoutError, ValueError, RuntimeError,
            OSError, IOError, AttributeError, TypeError,
        ]),
        error_message=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_returns_empty_list_on_any_exception(self, error_type, error_message):
        assume(error_message.strip())  # skip empty messages
        config = FeedConfig(name="test-p2", type="rss", url="https://example.com/feed")
        with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
            with patch("backend.scraper.rss.feedparser.parse",
                       side_effect=error_type(error_message)):
                scraper = RSSNewsScraper(config, lookback_hours=48)
                results = scraper.fetch()
        assert results == [], "fetch() must return [] on any exception"

    # Feature: ai-intel-dashboard, Property 2: Scraper resilience — failed source does not halt pipeline
    @given(
        bozo_reason=st.text(max_size=100),
        bozo_count=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_returns_empty_list_on_bozo_feed_with_no_entries(self, bozo_reason, bozo_count):
        entries = []
        for i in range(bozo_count):
            entries.append(feedparser.FeedParserDict({"link": f"https://example.com/{i}"}))
        config = FeedConfig(name="test-p2", type="rss", url="https://example.com/feed")
        with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
            with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
                mock_parse.return_value = feedparser.FeedParserDict({
                    "entries": entries,
                    "bozo": True,
                    "bozo_exception": Exception(bozo_reason) if bozo_reason else None,
                    "feed": feedparser.FeedParserDict({}),
                })
                scraper = RSSNewsScraper(config, lookback_hours=48)
                results = scraper.fetch()
        assert isinstance(results, list), "fetch() must always return a list"


# ---------------------------------------------------------------------------
# Property 3: Scraper output deduplication
# ---------------------------------------------------------------------------

@st.composite
def entries_with_duplicates(draw) -> list[feedparser.FeedParserDict]:
    """Generate feed entries where at least some share the same URL."""
    unique_url = draw(_url_strategy)
    dup_url = draw(_url_strategy)
    now = datetime.now(tz=timezone.utc)

    # Unique entry
    unique = feedparser.FeedParserDict({
        "link": unique_url,
        "title": "Unique",
        "published": "Mon, 01 Jan 2024 12:00:00 GMT",
        "published_parsed": _struct_time_from_dt(now - timedelta(hours=1)),
        "summary": "Unique summary",
    })
    # Two entries with the same URL (duplicate)
    dup1 = feedparser.FeedParserDict({
        "link": dup_url,
        "title": "Dup 1",
        "published": "Mon, 01 Jan 2024 12:00:00 GMT",
        "published_parsed": _struct_time_from_dt(now - timedelta(hours=2)),
        "summary": "Dup summary 1",
    })
    dup2 = feedparser.FeedParserDict({
        "link": dup_url,
        "title": "Dup 2",
        "published": "Mon, 02 Jan 2024 12:00:00 GMT",
        "published_parsed": _struct_time_from_dt(now - timedelta(hours=3)),
        "summary": "Dup summary 2",
    })
    return [unique, dup1, dup2]


class TestProperty3Deduplication:
    # Feature: ai-intel-dashboard, Property 3: Scraper output deduplication
    @given(entries=entries_with_duplicates())
    @settings(max_examples=100)
    def test_no_duplicate_urls_in_results(self, entries):
        config = FeedConfig(name="test-p3", type="rss", url="https://example.com/feed")
        with patch("backend.scraper.rss.httpx.Client", return_value=_mock_httpx()):
            with patch("backend.scraper.rss.feedparser.parse") as mock_parse:
                mock_parse.return_value = feedparser.FeedParserDict({
                    "entries": entries,
                    "bozo": False,
                    "bozo_exception": None,
                    "feed": feedparser.FeedParserDict({}),
                })
                scraper = RSSNewsScraper(config, lookback_hours=168)
                results = scraper.fetch()
        result_urls = [r["url"] for r in results]
        assert len(result_urls) == len(set(result_urls)), \
            "fetch() must not return duplicate URLs"
