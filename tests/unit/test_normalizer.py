"""Unit tests for backend.normalizer.normalizer (Tasks 10.1 & 10.2).

Covers:
- normalize() returns an Article with all fields from a valid record.
- normalize() returns None for a record missing title, url, or published_at.
- normalize() returns an Article (not None) with published_at=None for an
  unparseable timestamp.
- truncate_summary() truncates at the 2000-byte UTF-8 boundary.
- truncate_summary() leaves strings that fit within 2000 bytes unchanged.
- normalize_all() returns the correct articles list and discard_count.
- fetched_at is a UTC ISO 8601 string matching YYYY-MM-DDTHH:MM:SSZ.
- id is a valid UUID v4 string.
"""

from __future__ import annotations

import re
import uuid

import pytest

from backend.normalizer.normalizer import Normalizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _valid_raw(**overrides) -> dict:
    """Return a fully valid raw record, with optional field overrides."""
    base = {
        "title": "Some Article Title",
        "url": "https://example.com/article",
        "published_at": "2024-06-01T10:30:00+02:00",
        "source": "test-source",
        "summary": "Short summary.",
        "authors": ["Alice", "Bob"],
        "tags": ["ai", "ml"],
        "category": "NLP",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# normalize() — happy path
# ---------------------------------------------------------------------------

class TestNormalizeHappyPath:
    def setup_method(self):
        self.normalizer = Normalizer()

    def test_returns_article_for_valid_record(self):
        raw = _valid_raw()
        article = self.normalizer.normalize(raw)
        assert article is not None

    def test_title_is_preserved(self):
        raw = _valid_raw(title="My Title")
        article = self.normalizer.normalize(raw)
        assert article.title == "My Title"

    def test_url_is_preserved(self):
        raw = _valid_raw(url="https://example.com/x")
        article = self.normalizer.normalize(raw)
        assert article.url == "https://example.com/x"

    def test_source_is_preserved(self):
        raw = _valid_raw(source="my-source")
        article = self.normalizer.normalize(raw)
        assert article.source == "my-source"

    def test_source_defaults_to_empty_string_when_absent(self):
        raw = _valid_raw()
        del raw["source"]
        article = self.normalizer.normalize(raw)
        assert article.source == ""

    def test_category_is_preserved(self):
        raw = _valid_raw(category="Computer Vision")
        article = self.normalizer.normalize(raw)
        assert article.category == "Computer Vision"

    def test_category_defaults_to_none_when_absent(self):
        raw = _valid_raw()
        del raw["category"]
        article = self.normalizer.normalize(raw)
        assert article.category is None

    def test_authors_are_preserved(self):
        raw = _valid_raw(authors=["Alice", "Bob"])
        article = self.normalizer.normalize(raw)
        assert article.authors == ["Alice", "Bob"]

    def test_authors_defaults_to_empty_list_when_absent(self):
        raw = _valid_raw()
        del raw["authors"]
        article = self.normalizer.normalize(raw)
        assert article.authors == []

    def test_tags_are_preserved(self):
        raw = _valid_raw(tags=["nlp", "llm"])
        article = self.normalizer.normalize(raw)
        assert article.tags == ["nlp", "llm"]

    def test_tags_defaults_to_empty_list_when_absent(self):
        raw = _valid_raw()
        del raw["tags"]
        article = self.normalizer.normalize(raw)
        assert article.tags == []

    def test_raw_field_stores_original_dict_verbatim(self):
        raw = _valid_raw()
        article = self.normalizer.normalize(raw)
        assert article.raw is raw

    def test_summary_is_applied(self):
        raw = _valid_raw(summary="A summary text.")
        article = self.normalizer.normalize(raw)
        assert article.summary == "A summary text."

    def test_summary_none_when_absent(self):
        raw = _valid_raw()
        del raw["summary"]
        article = self.normalizer.normalize(raw)
        assert article.summary is None

    def test_summary_none_when_raw_summary_is_none(self):
        raw = _valid_raw(summary=None)
        article = self.normalizer.normalize(raw)
        assert article.summary is None


# ---------------------------------------------------------------------------
# normalize() — id and fetched_at
# ---------------------------------------------------------------------------

class TestNormalizeIdAndFetchedAt:
    def setup_method(self):
        self.normalizer = Normalizer()

    def test_id_is_uuid_v4_string(self):
        raw = _valid_raw()
        article = self.normalizer.normalize(raw)
        assert _UUID4_RE.match(article.id), f"Not a UUID v4: {article.id!r}"

    def test_id_is_unique_per_call(self):
        raw = _valid_raw()
        a1 = self.normalizer.normalize(raw)
        a2 = self.normalizer.normalize(raw)
        assert a1.id != a2.id

    def test_fetched_at_is_utc_iso8601(self):
        raw = _valid_raw()
        article = self.normalizer.normalize(raw)
        assert _ISO8601_UTC_RE.match(article.fetched_at), (
            f"fetched_at does not match YYYY-MM-DDTHH:MM:SSZ: {article.fetched_at!r}"
        )

    def test_fetched_at_ends_with_z(self):
        raw = _valid_raw()
        article = self.normalizer.normalize(raw)
        assert article.fetched_at.endswith("Z")


# ---------------------------------------------------------------------------
# normalize() — timestamp normalization
# ---------------------------------------------------------------------------

class TestNormalizeTimestamp:
    def setup_method(self):
        self.normalizer = Normalizer()

    def test_parses_iso8601_with_offset_to_utc(self):
        # +02:00 → subtract 2h → 08:30 UTC
        raw = _valid_raw(published_at="2024-06-01T10:30:00+02:00")
        article = self.normalizer.normalize(raw)
        assert article.published_at == "2024-06-01T08:30:00Z"

    def test_parses_utc_timestamp_unchanged(self):
        raw = _valid_raw(published_at="2024-01-15T12:00:00Z")
        article = self.normalizer.normalize(raw)
        assert article.published_at == "2024-01-15T12:00:00Z"

    def test_parses_naive_timestamp_as_local_but_produces_iso(self):
        # dateutil parses naive datetimes; result must still match the pattern.
        raw = _valid_raw(published_at="2024-01-15T12:00:00")
        article = self.normalizer.normalize(raw)
        assert article.published_at is not None
        assert _ISO8601_UTC_RE.match(article.published_at)

    def test_unparseable_timestamp_sets_published_at_to_none(self):
        raw = _valid_raw(published_at="not-a-date-at-all!!!")
        article = self.normalizer.normalize(raw)
        assert article is not None, "Record must be retained even with bad timestamp"
        assert article.published_at is None

    def test_unparseable_timestamp_retains_record(self):
        """normalize() must NOT return None when only the timestamp is bad."""
        raw = _valid_raw(published_at="???")
        result = self.normalizer.normalize(raw)
        assert result is not None


# ---------------------------------------------------------------------------
# normalize() — missing required fields returns None
# ---------------------------------------------------------------------------

class TestNormalizeMissingFields:
    def setup_method(self):
        self.normalizer = Normalizer()

    def test_returns_none_when_title_absent(self):
        raw = _valid_raw()
        del raw["title"]
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_title_is_none(self):
        raw = _valid_raw(title=None)
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_title_is_empty_string(self):
        raw = _valid_raw(title="")
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_url_absent(self):
        raw = _valid_raw()
        del raw["url"]
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_url_is_none(self):
        raw = _valid_raw(url=None)
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_url_is_empty_string(self):
        raw = _valid_raw(url="")
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_published_at_absent(self):
        raw = _valid_raw()
        del raw["published_at"]
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_published_at_is_none(self):
        raw = _valid_raw(published_at=None)
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_published_at_is_empty_string(self):
        raw = _valid_raw(published_at="")
        assert self.normalizer.normalize(raw) is None

    def test_returns_none_when_multiple_required_fields_absent(self):
        raw = {"source": "test"}
        assert self.normalizer.normalize(raw) is None

    def test_does_not_raise_for_missing_required_field(self):
        raw = {"source": "only-source"}
        try:
            result = self.normalizer.normalize(raw)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"normalize() raised unexpectedly: {exc}")
        assert result is None


# ---------------------------------------------------------------------------
# truncate_summary()
# ---------------------------------------------------------------------------

class TestTruncateSummary:
    def test_leaves_short_string_unchanged(self):
        s = "Hello world"
        assert Normalizer.truncate_summary(s) == s

    def test_leaves_exactly_2000_ascii_chars_unchanged(self):
        s = "a" * 2000
        result = Normalizer.truncate_summary(s)
        assert result == s
        assert len(result) == 2000

    def test_truncates_ascii_string_longer_than_2000_chars(self):
        s = "a" * 3000
        result = Normalizer.truncate_summary(s)
        assert len(result) == 2000

    def test_empty_string_unchanged(self):
        assert Normalizer.truncate_summary("") == ""

    def test_multibyte_unicode_within_limit_unchanged(self):
        # Each kanji = 3 UTF-8 bytes.  666 chars = 1998 bytes → fits.
        s = "あ" * 666
        result = Normalizer.truncate_summary(s)
        assert result == s

    def test_multibyte_unicode_truncated_at_byte_boundary(self):
        # Each kanji = 3 UTF-8 bytes.
        # 668 chars × 3 bytes = 2004 bytes → must truncate.
        s = "あ" * 668
        result = Normalizer.truncate_summary(s)
        # 2000 // 3 = 666 complete kanji (1998 bytes); the 2 remaining bytes
        # are dropped by errors='ignore', so result is 666 chars.
        assert len(result.encode("utf-8")) <= 2000
        # Result must be valid UTF-8 (encode/decode without error).
        result.encode("utf-8")

    def test_result_is_valid_utf8(self):
        # Mix ASCII and multi-byte chars, force truncation.
        s = "x" * 500 + "日本語テスト" * 200
        result = Normalizer.truncate_summary(s)
        assert len(result.encode("utf-8")) <= 2000
        result.encode("utf-8")  # must not raise

    def test_four_byte_emoji_boundary(self):
        # Each emoji (e.g. 😀) = 4 UTF-8 bytes.
        # 501 emojis × 4 = 2004 bytes → must truncate.
        s = "😀" * 501
        result = Normalizer.truncate_summary(s)
        assert len(result.encode("utf-8")) <= 2000
        result.encode("utf-8")


# ---------------------------------------------------------------------------
# normalize_all()
# ---------------------------------------------------------------------------

class TestNormalizeAll:
    def setup_method(self):
        self.normalizer = Normalizer()

    def test_empty_list_returns_empty_articles_and_zero_discards(self):
        articles, discards = self.normalizer.normalize_all([])
        assert articles == []
        assert discards == 0

    def test_all_valid_records_returns_all_articles_zero_discards(self):
        records = [_valid_raw(url=f"https://example.com/{i}") for i in range(5)]
        articles, discards = self.normalizer.normalize_all(records)
        assert len(articles) == 5
        assert discards == 0

    def test_all_invalid_records_returns_empty_articles_and_correct_discard_count(self):
        records = [{"source": "x"}, {"source": "y"}, {}]
        articles, discards = self.normalizer.normalize_all(records)
        assert articles == []
        assert discards == 3

    def test_mixed_records_splits_correctly(self):
        records = [
            _valid_raw(url="https://example.com/good1"),
            {"source": "bad1"},  # missing required fields
            _valid_raw(url="https://example.com/good2"),
            {"title": "no-url"},  # missing url and published_at
        ]
        articles, discards = self.normalizer.normalize_all(records)
        assert len(articles) == 2
        assert discards == 2

    def test_discard_count_matches_none_results(self):
        records = [
            _valid_raw(url="https://example.com/1"),
            _valid_raw(url=None),  # will be discarded
            _valid_raw(url="https://example.com/3"),
        ]
        articles, discards = self.normalizer.normalize_all(records)
        assert len(articles) == 2
        assert discards == 1

    def test_returned_articles_are_article_instances(self):
        from backend.models.article import Article

        records = [_valid_raw(url=f"https://example.com/{i}") for i in range(3)]
        articles, _ = self.normalizer.normalize_all(records)
        for art in articles:
            assert isinstance(art, Article)
