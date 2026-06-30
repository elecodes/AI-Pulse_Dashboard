"""Unit tests for HuggingFaceScraper.

Coverage (Requirements 4.1, 4.2, 4.3, 4.4):
1. fetch() with a normal API response → title, url, summary extracted correctly
2. fetch() when items have no native date → published_at falls back to fetch timestamp
3. fetch() when endpoint is unreachable → returns [], does not raise
4. fetch() when API returns non-200 → returns [], does not raise
5. URL deduplication: duplicate modelId → only one record returned
6. source_name returns the feed config name
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.config.config_loader import FeedConfig
from backend.scraper.huggingface import HuggingFaceScraper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed_config(
    name: str = "huggingface-trending",
    url: str = "https://huggingface.co/api/models",
) -> FeedConfig:
    return FeedConfig(name=name, type="huggingface", url=url)


def _mock_response(
    json_data: Any,
    status_code: int = 200,
) -> MagicMock:
    """Build a mock httpx.Response with a .json() method."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _make_client_mock(response: MagicMock) -> MagicMock:
    """Return a context-manager-compatible mock httpx.Client."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = response
    return mock_client


# ---------------------------------------------------------------------------
# Sample API payloads
# ---------------------------------------------------------------------------

_ITEM_WITH_DATES: dict[str, Any] = {
    "modelId": "bert-base-uncased",
    "id": "bert-base-uncased",
    "lastModified": "2024-01-15T10:00:00.000Z",
    "createdAt": "2022-01-01T00:00:00.000Z",
    "description": "BERT base model (uncased).",
    "likes": 1200,
}

_ITEM_WITHOUT_DATES: dict[str, Any] = {
    "modelId": "gpt2",
    "id": "gpt2",
    "description": "GPT-2 language model.",
    "likes": 800,
    # Intentionally no lastModified or createdAt
}

_ITEM_DUP_A: dict[str, Any] = {
    "modelId": "openai/whisper-large",
    "description": "First occurrence",
}

_ITEM_DUP_B: dict[str, Any] = {
    "modelId": "openai/whisper-large",
    "description": "Duplicate — should be dropped",
}


# ---------------------------------------------------------------------------
# 6. source_name
# ---------------------------------------------------------------------------

def test_source_name_returns_feed_config_name():
    """source_name must return the name from FeedConfig (Requirement 4.1)."""
    scraper = HuggingFaceScraper(_feed_config(name="hf-trending"), lookback_hours=48)
    assert scraper.source_name == "hf-trending"


# ---------------------------------------------------------------------------
# 1. Normal API response — field extraction
# ---------------------------------------------------------------------------

def test_fetch_extracts_title_from_model_id():
    """title should be the modelId value (Requirement 4.2)."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITH_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert len(results) == 1
    assert results[0]["title"] == "bert-base-uncased"


def test_fetch_constructs_url_from_model_id():
    """url should be https://huggingface.co/{modelId} (Requirement 4.2)."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITH_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results[0]["url"] == "https://huggingface.co/bert-base-uncased"


def test_fetch_extracts_summary_from_description():
    """summary should come from the description field (Requirement 4.2)."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITH_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results[0]["summary"] == "BERT base model (uncased)."


def test_fetch_summary_is_none_when_no_description():
    """summary should be None when description is absent (Requirement 4.2)."""
    item_no_desc: dict[str, Any] = {"modelId": "no-desc-model", "lastModified": "2024-01-01T00:00:00Z"}
    mock_client = _make_client_mock(_mock_response([item_no_desc]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results[0]["summary"] is None


def test_fetch_uses_last_modified_as_published_at_when_available():
    """published_at should use lastModified when present (Requirement 4.2)."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITH_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results[0]["published_at"] == "2024-01-15T10:00:00.000Z"


def test_fetch_falls_back_to_created_at_when_no_last_modified():
    """published_at should fall back to createdAt when lastModified absent (Requirement 4.2)."""
    item: dict[str, Any] = {
        "modelId": "some-model",
        "createdAt": "2023-06-01T08:30:00Z",
        # No lastModified
    }
    mock_client = _make_client_mock(_mock_response([item]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results[0]["published_at"] == "2023-06-01T08:30:00Z"


def test_fetch_source_field_equals_source_name():
    """The source field on each record should match source_name."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITH_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        scraper = HuggingFaceScraper(_feed_config(name="hf-models"), lookback_hours=48)
        results = scraper.fetch()

    assert results[0]["source"] == "hf-models"


def test_fetch_uses_id_field_when_model_id_absent():
    """title/url should fall back to 'id' when 'modelId' is missing."""
    item: dict[str, Any] = {
        "id": "facebook/bart-large",
        "description": "BART model.",
        "lastModified": "2024-02-01T00:00:00Z",
    }
    mock_client = _make_client_mock(_mock_response([item]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert len(results) == 1
    assert results[0]["title"] == "facebook/bart-large"
    assert results[0]["url"] == "https://huggingface.co/facebook/bart-large"


# ---------------------------------------------------------------------------
# 2. No native date → fallback to fetch timestamp
# ---------------------------------------------------------------------------

def test_fetch_sets_published_at_to_fetch_timestamp_when_no_native_date():
    """When neither lastModified nor createdAt is present, published_at must be
    a non-None string (the fetch timestamp fallback). Requirement 4.2."""
    mock_client = _make_client_mock(_mock_response([_ITEM_WITHOUT_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert len(results) == 1
    published_at = results[0]["published_at"]
    assert published_at is not None
    assert isinstance(published_at, str)
    assert len(published_at) > 0


def test_fetch_fallback_timestamp_is_iso8601_format():
    """The fallback published_at should look like a UTC ISO 8601 timestamp."""
    import re

    mock_client = _make_client_mock(_mock_response([_ITEM_WITHOUT_DATES]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    published_at = results[0]["published_at"]
    # Matches YYYY-MM-DDTHH:MM:SSZ
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    assert re.match(pattern, published_at), (
        f"published_at {published_at!r} does not match ISO 8601 UTC format"
    )


# ---------------------------------------------------------------------------
# 3. Endpoint unreachable → returns [], does not raise
# ---------------------------------------------------------------------------

def test_fetch_returns_empty_list_on_connection_error():
    """A connection-level exception → fetch() returns [] (Requirement 4.3)."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = Exception("Connection refused")

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results == []


def test_fetch_does_not_raise_on_connection_error():
    """fetch() must never propagate exceptions — only return [] (Requirement 4.3)."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = RuntimeError("timeout")

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        try:
            results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()
        except Exception as exc:
            pytest.fail(f"fetch() raised unexpectedly: {exc}")
        assert results == []


def test_fetch_logs_warning_on_connection_error(caplog: pytest.LogCaptureFixture):
    """A failed fetch must log a WARNING containing the source name."""
    import logging

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = RuntimeError("network failure")

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        with caplog.at_level(logging.WARNING, logger="backend.scraper.huggingface"):
            HuggingFaceScraper(_feed_config(name="hf-down"), lookback_hours=48).fetch()

    assert any("hf-down" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 4. API returns non-200 → returns [], does not raise
# ---------------------------------------------------------------------------

def test_fetch_returns_empty_list_on_http_404():
    """HTTP 404 → fetch() returns [] (Requirement 4.3)."""
    mock_client = _make_client_mock(_mock_response([], status_code=404))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results == []


def test_fetch_returns_empty_list_on_http_500():
    """HTTP 500 → fetch() returns [] (Requirement 4.3)."""
    mock_client = _make_client_mock(_mock_response([], status_code=500))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert results == []


def test_fetch_does_not_raise_on_non_200():
    """fetch() must not raise on any non-200 response."""
    mock_client = _make_client_mock(_mock_response("error", status_code=503))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        try:
            results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()
        except Exception as exc:
            pytest.fail(f"fetch() raised unexpectedly: {exc}")
        assert results == []


# ---------------------------------------------------------------------------
# 5. URL deduplication
# ---------------------------------------------------------------------------

def test_fetch_deduplicates_by_model_id_keeps_first():
    """Two items with the same modelId → only first record kept (Requirement 4.4)."""
    mock_client = _make_client_mock(_mock_response([_ITEM_DUP_A, _ITEM_DUP_B]))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert len(results) == 1
    assert results[0]["summary"] == "First occurrence"


def test_fetch_no_duplicate_urls_in_output():
    """Output must contain no two records sharing the same url (Requirement 4.4)."""
    items = [_ITEM_DUP_A, _ITEM_DUP_B, _ITEM_WITH_DATES]
    mock_client = _make_client_mock(_mock_response(items))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls)), "Duplicate URLs found in fetch() output"


def test_fetch_distinct_model_ids_both_returned():
    """Two items with different modelIds should both appear in output."""
    items = [_ITEM_WITH_DATES, _ITEM_WITHOUT_DATES]
    mock_client = _make_client_mock(_mock_response(items))

    with patch("backend.scraper.huggingface.httpx.Client", return_value=mock_client):
        results = HuggingFaceScraper(_feed_config(), lookback_hours=48).fetch()

    assert len(results) == 2
