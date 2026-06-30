"""Property-based tests for Normalizer (Properties 4, 5, 6, 7).

# Feature: ai-intel-dashboard, Property 4: Normalizer produces complete Article from valid record
# Feature: ai-intel-dashboard, Property 5: Normalizer discards records missing required fields
# Feature: ai-intel-dashboard, Property 6: Timestamp normalization to UTC ISO 8601
# Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from hypothesis import assume, given, settings, strategies as st

from backend.normalizer.normalizer import Normalizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISO8601_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)

# Valid raw record strategy — all required fields are present
_valid_raw_record = st.fixed_dictionaries(
    {
        "title": st.text(min_size=1, max_size=100).filter(bool),
        "url": st.from_regex(r"https?://[a-z0-9.-]+/\S*", fullmatch=False).filter(
            lambda s: len(s) > 0
        ),
        "published_at": st.datetimes().map(lambda dt: dt.isoformat()),
        "source": st.text(max_size=50),
        "summary": st.text(max_size=500),
        "authors": st.lists(st.text(max_size=50), max_size=5),
        "tags": st.lists(st.text(max_size=30), max_size=5),
    },
)


# ---------------------------------------------------------------------------
# Property 4: Normalizer produces a complete Article from any valid record
# ---------------------------------------------------------------------------

class TestProperty4CompleteArticle:
    # Feature: ai-intel-dashboard, Property 4: Normalizer produces complete Article from valid record
    @given(raw=_valid_raw_record)
    @settings(max_examples=100)
    def test_all_schema_fields_present(self, raw):
        normalizer = Normalizer()
        result = normalizer.normalize(raw)
        assert result is not None, "Normalizer must return Article for valid record"
        assert isinstance(result.id, str), "id must be a string"
        assert uuid.UUID(result.id).version == 4, "id must be UUID v4"
        assert _ISO8601_UTC_RE.match(result.fetched_at), \
            f"fetched_at must be UTC ISO 8601, got {result.fetched_at!r}"
        assert isinstance(result.authors, list), "authors must be a list"
        assert isinstance(result.tags, list), "tags must be a list"
        assert result.raw is raw, "raw must preserve input verbatim"


# ---------------------------------------------------------------------------
# Property 5: Normalizer discards records missing required fields
# ---------------------------------------------------------------------------

class TestProperty5DiscardsMissing:
    # Feature: ai-intel-dashboard, Property 5: Normalizer discards records missing required fields
    @given(
        extra=st.dictionaries(
            st.text(max_size=20),
            st.text(max_size=50),
            max_size=5,
        ),
        missing_field=st.sampled_from(["title", "url", "published_at"]),
    )
    @settings(max_examples=100)
    def test_returns_none_when_required_field_missing(self, extra, missing_field):
        raw: dict[str, Any] = {
            "title": "Test Title",
            "url": "https://example.com/article",
            "published_at": "2024-01-15T12:00:00Z",
        }
        raw.update(extra)
        del raw[missing_field]
        normalizer = Normalizer()
        result = normalizer.normalize(raw)
        assert result is None, \
            f"normalize() must return None when {missing_field!r} is missing"


# ---------------------------------------------------------------------------
# Property 6: Timestamp normalization to UTC ISO 8601
# ---------------------------------------------------------------------------

@st.composite
def parseable_timestamp(draw) -> str:
    """Generate a parseable timestamp string in various formats."""
    dt = draw(st.datetimes())
    format_choice = draw(st.sampled_from([
        lambda d: d.isoformat(),
        lambda d: d.strftime("%Y-%m-%d %H:%M:%S"),
        lambda d: d.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        lambda d: d.strftime("%Y%m%dT%H%M%S"),
        lambda d: d.strftime("%m/%d/%Y %H:%M:%S"),
    ]))
    return format_choice(dt)


@st.composite
def unparseable_timestamp(draw) -> str:
    """Generate a string that cannot be parsed as a timestamp."""
    return draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        min_size=1, max_size=30,
    ).filter(
        lambda s: not any(c.isdigit() for c in s[:5])
    ))


class TestProperty6TimestampNormalization:
    # Feature: ai-intel-dashboard, Property 6: Timestamp normalization to UTC ISO 8601
    @given(ts=parseable_timestamp())
    @settings(max_examples=100)
    def test_parseable_timestamp_produces_iso8601_utc(self, ts):
        assume(len(ts) > 0)
        normalizer = Normalizer()
        result = normalizer._parse_timestamp(ts)
        assert result is not None, f"Parseable timestamp {ts!r} must not return None"
        assert _ISO8601_UTC_RE.match(result), \
            f"Output {result!r} must match UTC ISO 8601"

    # Feature: ai-intel-dashboard, Property 6: Timestamp normalization to UTC ISO 8601
    @given(ts=unparseable_timestamp())
    @settings(max_examples=100)
    def test_unparseable_timestamp_returns_none(self, ts):
        normalizer = Normalizer()
        result = normalizer._parse_timestamp(ts)
        assert result is None, f"Unparseable timestamp {ts!r} must return None"

    # Feature: ai-intel-dashboard, Property 6: Timestamp normalization to UTC ISO 8601
    @given(raw=st.fixed_dictionaries({
        "title": st.just("Test"),
        "url": st.just("https://example.com/a"),
        "published_at": unparseable_timestamp(),
    }))
    @settings(max_examples=100)
    def test_unparseable_timestamp_retains_record(self, raw):
        normalizer = Normalizer()
        result = normalizer.normalize(raw)
        assert result is not None, \
            "Record with unparseable timestamp must not be discarded"
        assert result.published_at is None, \
            "published_at must be None when timestamp is unparseable"


# ---------------------------------------------------------------------------
# Property 7: Summary truncation preserves UTF-8 boundary
# ---------------------------------------------------------------------------

class TestProperty7SummaryTruncation:
    # Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary
    @given(s=st.text(max_size=5000))
    @settings(max_examples=100)
    def test_never_exceeds_2000_bytes(self, s):
        normalizer = Normalizer()
        result = normalizer.truncate_summary(s)
        encoded = result.encode("utf-8")
        assert len(encoded) <= 2000, \
            f"Truncated UTF-8 length ({len(encoded)}) exceeds 2000 bytes"

    # Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary
    @given(s=st.text(max_size=5000))
    @settings(max_examples=100)
    def test_result_is_valid_utf8(self, s):
        normalizer = Normalizer()
        result = normalizer.truncate_summary(s)
        encoded = result.encode("utf-8")
        decoded = encoded.decode("utf-8")
        assert decoded == result

    # Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary
    @given(s=st.text(max_size=1999))
    @settings(max_examples=100)
    def test_short_string_unchanged(self, s):
        normalizer = Normalizer()
        result = normalizer.truncate_summary(s)
        assert result == s, "Strings ≤ 2000 chars must be returned unchanged"

    # Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary
    @given(s=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "M")),
        min_size=0, max_size=5000,
    ))
    @settings(max_examples=100)
    def test_multibyte_truncation_at_byte_boundary(self, s):
        normalizer = Normalizer()
        result = normalizer.truncate_summary(s)
        encoded = result.encode("utf-8")
        assert len(encoded) <= 2000, "Must not exceed 2000 bytes"
        if len(s.encode("utf-8")) > 2000:
            assert len(result) < len(s), \
                "Long strings must be truncated (not just character count)"
