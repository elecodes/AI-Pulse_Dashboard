"""Unit tests for backend.models.article.Article (Task 2.1).

Covers:
- All fields are stored correctly.
- to_json() produces valid, deterministic JSON with sort_keys.
- from_json() reconstructs an identical Article.
- Round-trip: to_json(from_json(to_json(a))) == to_json(a).
- Default factory fields (authors, tags) default to empty lists.
- category and published_at default to None.
- Non-serializable values inside raw do not raise in to_json().
- from_json() raises on invalid JSON and on missing required fields.
"""

import json

import pytest

from backend.models.article import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(**overrides) -> Article:
    """Return a fully-populated Article, with optional field overrides."""
    defaults = dict(
        id="550e8400-e29b-41d4-a716-446655440000",
        title="Test Article",
        url="https://example.com/article",
        source="test-source",
        published_at="2024-01-15T12:00:00Z",
        fetched_at="2024-01-15T13:00:00Z",
        summary="A short summary.",
        authors=["Alice", "Bob"],
        tags=["ai", "ml"],
        category="research",
        raw={"original_key": "original_value"},
    )
    defaults.update(overrides)
    return Article(**defaults)


# ---------------------------------------------------------------------------
# Field storage
# ---------------------------------------------------------------------------

class TestArticleFields:
    def test_all_fields_stored_correctly(self):
        a = make_article()
        assert a.id == "550e8400-e29b-41d4-a716-446655440000"
        assert a.title == "Test Article"
        assert a.url == "https://example.com/article"
        assert a.source == "test-source"
        assert a.published_at == "2024-01-15T12:00:00Z"
        assert a.fetched_at == "2024-01-15T13:00:00Z"
        assert a.summary == "A short summary."
        assert a.authors == ["Alice", "Bob"]
        assert a.tags == ["ai", "ml"]
        assert a.category == "research"
        assert a.raw == {"original_key": "original_value"}

    def test_published_at_can_be_none(self):
        a = make_article(published_at=None)
        assert a.published_at is None

    def test_summary_can_be_none(self):
        a = make_article(summary=None)
        assert a.summary is None

    def test_category_can_be_none(self):
        a = make_article(category=None)
        assert a.category is None

    def test_authors_defaults_to_empty_list(self):
        a = Article(
            id="x", title="t", url="u", source="s",
            published_at=None, fetched_at="2024-01-01T00:00:00Z",
            summary=None,
        )
        assert a.authors == []

    def test_tags_defaults_to_empty_list(self):
        a = Article(
            id="x", title="t", url="u", source="s",
            published_at=None, fetched_at="2024-01-01T00:00:00Z",
            summary=None,
        )
        assert a.tags == []

    def test_authors_and_tags_are_independent_instances(self):
        """Default factory must not share the same list across instances."""
        a1 = Article(
            id="1", title="t", url="u1", source="s",
            published_at=None, fetched_at="2024-01-01T00:00:00Z",
            summary=None,
        )
        a2 = Article(
            id="2", title="t", url="u2", source="s",
            published_at=None, fetched_at="2024-01-01T00:00:00Z",
            summary=None,
        )
        a1.authors.append("Alice")
        assert a2.authors == [], "default_factory lists must not be shared"


# ---------------------------------------------------------------------------
# to_json
# ---------------------------------------------------------------------------

class TestToJson:
    def test_returns_valid_json_string(self):
        a = make_article()
        parsed = json.loads(a.to_json())
        assert isinstance(parsed, dict)

    def test_keys_are_sorted(self):
        a = make_article()
        raw_json = a.to_json()
        parsed = json.loads(raw_json)
        keys = list(parsed.keys())
        assert keys == sorted(keys), "to_json must use sort_keys=True"

    def test_all_fields_present_in_json(self):
        a = make_article()
        parsed = json.loads(a.to_json())
        expected_keys = {
            "id", "title", "url", "source", "published_at", "fetched_at",
            "summary", "authors", "tags", "category", "classification_failed",
            "raw",
        }
        assert expected_keys == set(parsed.keys())

    def test_none_fields_serialized_as_null(self):
        a = make_article(published_at=None, summary=None, category=None)
        parsed = json.loads(a.to_json())
        assert parsed["published_at"] is None
        assert parsed["summary"] is None
        assert parsed["category"] is None

    def test_deterministic_output(self):
        """Same Article always produces the same JSON string."""
        a = make_article()
        assert a.to_json() == a.to_json()

    def test_non_serializable_raw_does_not_raise(self):
        """Non-JSON-serializable values in raw must not cause to_json() to raise."""

        class NonSerializable:
            def __repr__(self):
                return "NonSerializable()"

        a = make_article(raw={"obj": NonSerializable()})
        result = a.to_json()  # must not raise
        parsed = json.loads(result)
        assert "obj" in parsed["raw"]


# ---------------------------------------------------------------------------
# from_json
# ---------------------------------------------------------------------------

class TestFromJson:
    def test_reconstructs_article_from_json(self):
        original = make_article()
        restored = Article.from_json(original.to_json())
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.url == original.url
        assert restored.source == original.source
        assert restored.published_at == original.published_at
        assert restored.fetched_at == original.fetched_at
        assert restored.summary == original.summary
        assert restored.authors == original.authors
        assert restored.tags == original.tags
        assert restored.category == original.category
        assert restored.raw == original.raw

    def test_from_json_with_null_optional_fields(self):
        a = make_article(published_at=None, summary=None, category=None)
        restored = Article.from_json(a.to_json())
        assert restored.published_at is None
        assert restored.summary is None
        assert restored.category is None

    def test_raises_on_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            Article.from_json("not-valid-json{{{")

    def test_raises_on_missing_required_field(self):
        data = {
            "id": "x", "title": "t", "url": "u", "source": "s",
            "published_at": None, "fetched_at": "2024-01-01T00:00:00Z",
            "summary": None,
            # "authors", "tags", "category", "raw" are optional via .get()
        }
        # Remove a required field to trigger KeyError
        del data["title"]
        with pytest.raises(KeyError):
            Article.from_json(json.dumps(data))


# ---------------------------------------------------------------------------
# Round-trip property (example-based)
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_serialize_deserialize_serialize_is_idempotent(self):
        """serialize(deserialize(serialize(A))) == serialize(A)  (Property 8 example)."""
        a = make_article()
        s1 = a.to_json()
        s2 = Article.from_json(s1).to_json()
        assert s1 == s2

    def test_round_trip_with_empty_lists(self):
        a = make_article(authors=[], tags=[])
        s1 = a.to_json()
        s2 = Article.from_json(s1).to_json()
        assert s1 == s2

    def test_round_trip_with_none_published_at(self):
        a = make_article(published_at=None)
        s1 = a.to_json()
        s2 = Article.from_json(s1).to_json()
        assert s1 == s2

    def test_round_trip_with_unicode_content(self):
        a = make_article(title="こんにちは世界", summary="Héllo wörld 🌍")
        s1 = a.to_json()
        s2 = Article.from_json(s1).to_json()
        assert s1 == s2
