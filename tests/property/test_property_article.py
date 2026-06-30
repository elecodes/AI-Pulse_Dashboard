"""Property-based test for Article round-trip (Property 8).

# Feature: ai-intel-dashboard, Property 8: Article serialization round-trip
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from backend.models.article import Article


# ---------------------------------------------------------------------------
# Strategy for generating valid Article instances
# ---------------------------------------------------------------------------

_article_strategy = st.builds(
    Article,
    id=st.text(min_size=1, max_size=40),
    title=st.text(max_size=100),
    url=st.from_regex(r"https?://[a-z0-9.-]+/\S*", fullmatch=False).filter(
        lambda s: len(s) > 0
    ),
    source=st.text(max_size=50),
    published_at=st.one_of(st.none(), st.text(max_size=30)),
    fetched_at=st.text(min_size=1, max_size=30),
    summary=st.one_of(st.none(), st.text(max_size=500)),
    authors=st.lists(st.text(max_size=50), max_size=5),
    tags=st.lists(st.text(max_size=30), max_size=5),
    category=st.one_of(st.none(), st.text(max_size=50)),
    raw=st.dictionaries(
        st.text(max_size=20),
        st.text(max_size=100),
        max_size=5,
    ),
)


class TestProperty8RoundTrip:
    # Feature: ai-intel-dashboard, Property 8: Article serialization round-trip
    @given(article=_article_strategy)
    @settings(max_examples=100)
    def test_serialize_deserialize_serialize_is_idempotent(self, article):
        s1 = article.to_json()
        s2 = Article.from_json(s1).to_json()
        assert s1 == s2, \
            "serialize(deserialize(serialize(A))) must equal serialize(A)"
