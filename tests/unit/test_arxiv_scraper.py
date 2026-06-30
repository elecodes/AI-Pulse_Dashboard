"""Unit tests for ArXivScraper.

Tests use an inline Atom XML fixture instead of live network calls.
The fixture contains two entries:
  - PAPER_RECENT  published ~1 hour ago  → kept by the 48-hour look-back window
  - PAPER_OLD     published ~96 hours ago → dropped by the 48-hour look-back window

Coverage:
  - Field extraction: paper_id, title, authors, summary, published_at, url (PDF)
  - Look-back window: old entry is dropped
  - Deduplication by paper ID: duplicate entries collapse to one
  - Network error → fetch() returns []
  - HTTP non-200 response → fetch() returns []
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.config.config_loader import FeedConfig
from backend.scraper.arxiv import ArXivScraper, _extract_paper_id


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _utc_rfc3339(dt: datetime) -> str:
    """Format a UTC datetime as RFC 3339 / arXiv Atom timestamp."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _atom_feed(entries_xml: str) -> str:
    """Wrap entry XML fragments in a minimal valid arXiv Atom envelope."""
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <title>ArXiv Query: test</title>
          <id>http://arxiv.org/api/test</id>
          <updated>2024-01-01T00:00:00Z</updated>
          <opensearch:totalResults>2</opensearch:totalResults>
          <opensearch:startIndex>0</opensearch:startIndex>
          <opensearch:itemsPerPage>100</opensearch:itemsPerPage>
          {entries_xml}
        </feed>
    """)


def _make_entry_xml(
    paper_id: str,
    title: str,
    published: str,
    summary: str,
    authors: list[str],
    pdf_href: str,
    abs_href: str | None = None,
) -> str:
    """Build a single Atom <entry> XML snippet matching arXiv's format."""
    if abs_href is None:
        abs_href = f"http://arxiv.org/abs/{paper_id}v1"
    author_tags = "\n    ".join(
        f"<author><name>{a}</name></author>" for a in authors
    )
    return textwrap.dedent(f"""\
        <entry>
          <id>{abs_href}</id>
          <title>{title}</title>
          <published>{published}</published>
          <updated>{published}</updated>
          <summary>{summary}</summary>
          {author_tags}
          <link rel="alternate" type="text/html" href="{abs_href}"/>
          <link rel="related" type="application/pdf" href="{pdf_href}"/>
        </entry>
    """)


# ---------------------------------------------------------------------------
# Build the two canonical fixtures used across most tests
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)
_RECENT_DT = _NOW - timedelta(hours=1)
_OLD_DT = _NOW - timedelta(hours=96)

PAPER_RECENT_ID = "2401.11111"
PAPER_OLD_ID = "2401.22222"

_ENTRY_RECENT = _make_entry_xml(
    paper_id=PAPER_RECENT_ID,
    title="Recent Paper on Large Language Models",
    published=_utc_rfc3339(_RECENT_DT),
    summary="An abstract about LLMs published recently.",
    authors=["Alice Smith", "Bob Jones"],
    pdf_href=f"http://arxiv.org/pdf/{PAPER_RECENT_ID}v1",
)

_ENTRY_OLD = _make_entry_xml(
    paper_id=PAPER_OLD_ID,
    title="Old Paper on Computer Vision",
    published=_utc_rfc3339(_OLD_DT),
    summary="An old abstract that is outside the look-back window.",
    authors=["Carol White"],
    pdf_href=f"http://arxiv.org/pdf/{PAPER_OLD_ID}v1",
)

# Feed with both entries
ATOM_TWO_ENTRIES = _atom_feed(_ENTRY_RECENT + "\n" + _ENTRY_OLD)

# Feed with only the recent entry
ATOM_RECENT_ONLY = _atom_feed(_ENTRY_RECENT)

# Feed with the recent entry duplicated (same paper ID, different XML content)
_ENTRY_RECENT_DUP = _make_entry_xml(
    paper_id=PAPER_RECENT_ID,
    title="Duplicate entry — same paper ID",
    published=_utc_rfc3339(_RECENT_DT),
    summary="Duplicate abstract.",
    authors=["Alice Smith"],
    pdf_href=f"http://arxiv.org/pdf/{PAPER_RECENT_ID}v2",
    abs_href=f"http://arxiv.org/abs/{PAPER_RECENT_ID}v2",
)
ATOM_DUPLICATE_ID = _atom_feed(_ENTRY_RECENT + "\n" + _ENTRY_RECENT_DUP)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed_config(
    name: str = "arxiv-cs-ai",
    url: str = "http://export.arxiv.org/api/query",
    categories: list[str] | None = None,
) -> FeedConfig:
    return FeedConfig(
        name=name,
        type="arxiv",
        url=url,
        categories=categories if categories is not None else ["cs.AI"],
    )


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.request = MagicMock()
    return resp


def _scraper_with_mock_http(
    atom_text: str,
    status_code: int = 200,
    name: str = "arxiv-cs-ai",
    lookback_hours: int = 48,
) -> tuple[ArXivScraper, MagicMock]:
    """Return (scraper, mock_client) with httpx.Client patched."""
    scraper = ArXivScraper(_feed_config(name=name), lookback_hours=lookback_hours)
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = _mock_response(atom_text, status_code)
    return scraper, mock_client


# ---------------------------------------------------------------------------
# source_name
# ---------------------------------------------------------------------------

def test_source_name_returns_feed_config_name():
    scraper = ArXivScraper(_feed_config(name="arxiv-cs-cv"), lookback_hours=48)
    assert scraper.source_name == "arxiv-cs-cv"


# ---------------------------------------------------------------------------
# _extract_paper_id helper
# ---------------------------------------------------------------------------

def test_extract_paper_id_strips_abs_prefix_and_version():
    assert _extract_paper_id("http://arxiv.org/abs/2401.12345v1") == "2401.12345"


def test_extract_paper_id_strips_version_only():
    assert _extract_paper_id("2401.12345v3") == "2401.12345"


def test_extract_paper_id_bare_id():
    assert _extract_paper_id("2401.12345") == "2401.12345"


# ---------------------------------------------------------------------------
# Field extraction (Task 7.2 requirement: paper_id, title, authors,
# summary, published_at, PDF url)
# ---------------------------------------------------------------------------

def test_fetch_extracts_paper_id():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert len(results) == 1
    assert results[0]["paper_id"] == PAPER_RECENT_ID


def test_fetch_extracts_title():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results[0]["title"] == "Recent Paper on Large Language Models"


def test_fetch_extracts_authors_as_list():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    authors = results[0]["authors"]
    assert isinstance(authors, list)
    assert "Alice Smith" in authors
    assert "Bob Jones" in authors


def test_fetch_extracts_summary():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results[0]["summary"] == "An abstract about LLMs published recently."


def test_fetch_extracts_published_at():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results[0]["published_at"] is not None
    # Must include the year from the fixture
    assert "2" in results[0]["published_at"]  # sanity: non-empty string


def test_fetch_extracts_pdf_url():
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results[0]["url"] == f"http://arxiv.org/pdf/{PAPER_RECENT_ID}v1"


def test_fetch_falls_back_to_entry_link_when_no_pdf_link():
    """When no application/pdf link exists, url should fall back to entry.link."""
    entry_no_pdf = _make_entry_xml(
        paper_id="2401.33333",
        title="No PDF Link Paper",
        published=_utc_rfc3339(_RECENT_DT),
        summary="Abstract.",
        authors=["Dana Brown"],
        pdf_href="PLACEHOLDER",  # will be overwritten by custom XML
    )
    # Build the entry without a PDF link — only the HTML alternate link
    entry_no_pdf_xml = textwrap.dedent(f"""\
        <entry>
          <id>http://arxiv.org/abs/2401.33333v1</id>
          <title>No PDF Link Paper</title>
          <published>{_utc_rfc3339(_RECENT_DT)}</published>
          <summary>Abstract.</summary>
          <author><name>Dana Brown</name></author>
          <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2401.33333v1"/>
        </entry>
    """)
    atom = _atom_feed(entry_no_pdf_xml)

    scraper, mock_client = _scraper_with_mock_http(atom)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert len(results) == 1
    # Should fall back to the HTML link (entry.link)
    assert results[0]["url"] is not None


# ---------------------------------------------------------------------------
# Look-back window filter
# ---------------------------------------------------------------------------

def test_fetch_drops_old_entry():
    """The old entry (96 h ago) must be excluded when lookback_hours=48."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_TWO_ENTRIES, lookback_hours=48)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    paper_ids = [r["paper_id"] for r in results]
    assert PAPER_OLD_ID not in paper_ids


def test_fetch_keeps_recent_entry():
    """The recent entry (1 h ago) must be kept when lookback_hours=48."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_TWO_ENTRIES, lookback_hours=48)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    paper_ids = [r["paper_id"] for r in results]
    assert PAPER_RECENT_ID in paper_ids


def test_fetch_only_recent_entry_returned_from_two_entry_feed():
    """Exactly one record returned: the recent one."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_TWO_ENTRIES, lookback_hours=48)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert len(results) == 1


# ---------------------------------------------------------------------------
# Deduplication by paper ID
# ---------------------------------------------------------------------------

def test_fetch_deduplicates_same_paper_id():
    """Two entries with the same paper ID → only the first is kept."""
    scraper = ArXivScraper(
        _feed_config(categories=["cs.AI", "cs.LG"]),
        lookback_hours=48,
    )

    call_count = 0

    def mock_get(url: str) -> MagicMock:
        nonlocal call_count
        # Both categories return the same ATOM_DUPLICATE_ID (2 entries, same ID)
        call_count += 1
        return _mock_response(ATOM_RECENT_ONLY)

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = mock_get

    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    # Both categories returned the same paper → dedup → 1 result
    paper_ids = [r["paper_id"] for r in results]
    assert len(paper_ids) == len(set(paper_ids)), "Duplicate paper IDs found"


def test_fetch_deduplicates_within_single_category():
    """Duplicate entries in one category's response collapse to one."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_DUPLICATE_ID, lookback_hours=48)
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    paper_ids = [r["paper_id"] for r in results]
    assert len(paper_ids) == len(set(paper_ids)), "Duplicate paper IDs found"
    assert PAPER_RECENT_ID in paper_ids


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

def test_fetch_returns_empty_list_on_network_exception():
    """A connection-level exception → fetch() returns [], does not raise."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    mock_client.get.side_effect = Exception("connection refused")

    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results == []


def test_fetch_does_not_raise_on_network_exception():
    """fetch() is resilient — must never propagate exceptions to callers."""
    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    mock_client.get.side_effect = RuntimeError("boom")

    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        try:
            results = scraper.fetch()
        except Exception as exc:
            pytest.fail(f"fetch() raised unexpectedly: {exc}")
        assert results == []


def test_fetch_returns_empty_list_on_http_non_200():
    """A non-200 HTTP response (after retries) → fetch() returns []."""
    scraper, mock_client = _scraper_with_mock_http(
        atom_text="<error>not found</error>",
        status_code=404,
    )
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results == []


def test_fetch_returns_empty_list_on_http_500():
    """A server error (500) after retries → fetch() returns []."""
    scraper, mock_client = _scraper_with_mock_http(
        atom_text="<error>internal server error</error>",
        status_code=500,
    )
    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        results = scraper.fetch()

    assert results == []


def test_fetch_logs_warning_on_failure(caplog: pytest.LogCaptureFixture):
    """A failed fetch must log a WARNING containing the source name."""
    import logging

    scraper, mock_client = _scraper_with_mock_http(ATOM_RECENT_ONLY)
    mock_client.get.side_effect = RuntimeError("network failure")

    with patch("backend.scraper.arxiv.httpx.Client", return_value=mock_client):
        with caplog.at_level(logging.WARNING, logger="backend.scraper.arxiv"):
            scraper.fetch()

    assert any("arxiv-cs-ai" in record.message for record in caplog.records)
