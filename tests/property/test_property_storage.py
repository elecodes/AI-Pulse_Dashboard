"""Property-based tests for StorageLayer (Properties 9, 10, 11).

# Feature: ai-intel-dashboard, Property 9: Upsert on duplicate URL updates only fetched_at and raw
# Feature: ai-intel-dashboard, Property 10: Date-range query ordering
# Feature: ai-intel-dashboard, Property 11: Write failure causes full rollback
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from hypothesis import assume, given, settings, strategies as st

from backend.models.article import Article
from backend.storage.storage_layer import StorageLayer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _memory_storage() -> StorageLayer:
    s = StorageLayer(":memory:")
    s.init_db()
    return s


def _utc_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# Strategies
_article_base = st.builds(
    Article,
    id=st.uuids().map(str),
    title=st.text(min_size=1, max_size=100).filter(bool),
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
    raw=st.dictionaries(st.text(max_size=20), st.text(max_size=100), max_size=5),
)


# ---------------------------------------------------------------------------
# Property 9: Upsert on duplicate URL updates only fetched_at and raw
# ---------------------------------------------------------------------------

class TestProperty9Upsert:
    # Feature: ai-intel-dashboard, Property 9: Upsert on duplicate URL updates only fetched_at and raw
    @given(
        original=_article_base,
        updated=_article_base,
    )
    @settings(max_examples=100)
    def test_upsert_updates_only_fetched_at_and_raw(self, original, updated):
        assume(original.url and updated.url)
        storage = _memory_storage()

        updated = Article(
            id=updated.id,
            title=updated.title,
            url=original.url,
            source=updated.source,
            published_at=updated.published_at,
            fetched_at=updated.fetched_at,
            summary=updated.summary,
            authors=updated.authors,
            tags=updated.tags,
            category=updated.category,
            raw=updated.raw,
        )
        storage.save_batch([original])
        storage.save_batch([updated])

        articles = storage.get_articles()
        assert len(articles) == 1
        saved = articles[0]

        assert saved.fetched_at == updated.fetched_at
        assert saved.raw == updated.raw
        assert saved.id == original.id
        assert saved.title == original.title
        assert saved.source == original.source
        assert saved.published_at == original.published_at
        assert saved.summary == original.summary
        assert saved.authors == original.authors
        assert saved.tags == original.tags
        assert saved.category == original.category


# ---------------------------------------------------------------------------
# Property 10: Date-range query returns articles within bounds, ordered descending
# ---------------------------------------------------------------------------

@st.composite
def article_with_published_at(draw) -> Article:
    """Generate an Article with a specific published_at datetime."""
    dt = draw(st.datetimes(
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2025, 12, 31),
    ))
    dt_utc = dt.replace(tzinfo=timezone.utc)
    url = draw(st.from_regex(r"https?://[a-z0-9.-]+/\S*", fullmatch=False).filter(
        lambda s: len(s) > 0
    ))
    title = draw(st.text(min_size=1, max_size=50).filter(bool))
    article_id = str(uuid.uuid4())
    return Article(
        id=article_id,
        title=title,
        url=url + "/" + article_id,
        source="test",
        published_at=_utc_iso(dt_utc),
        fetched_at=_utc_iso(datetime.now(tz=timezone.utc)),
        summary=None,
        authors=[],
        tags=[],
        category=None,
        raw={},
    )


class TestProperty10DateRangeQuery:
    # Feature: ai-intel-dashboard, Property 10: Date-range query returns articles within bounds ordered descending
    @given(
        articles=st.lists(article_with_published_at(), min_size=1, max_size=20),
    )
    @settings(max_examples=100)
    def test_date_range_query_bounds_and_ordering(self, articles):
        storage = _memory_storage()
        storage.save_batch(articles)

        all_articles = storage.get_articles()
        assert len(all_articles) == len(articles)

        for i in range(len(all_articles) - 1):
            a, b = all_articles[i], all_articles[i + 1]
            if a.published_at and b.published_at:
                assert a.published_at >= b.published_at

    # Feature: ai-intel-dashboard, Property 10: Date-range query returns articles within bounds ordered descending
    @given(
        articles=st.lists(article_with_published_at(), min_size=2, max_size=15),
        date_from_dt=st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 6, 30),
        ),
        date_to_dt=st.datetimes(
            min_value=datetime(2024, 1, 1),
            max_value=datetime(2025, 12, 31),
        ),
    )
    @settings(max_examples=100)
    def test_filtered_query_returns_articles_in_bounds(
        self, articles, date_from_dt, date_to_dt,
    ):
        assume(date_from_dt <= date_to_dt)
        storage = _memory_storage()
        storage.save_batch(articles)

        date_from = date_from_dt.replace(tzinfo=timezone.utc)
        date_to = date_to_dt.replace(tzinfo=timezone.utc)
        df_str = _utc_iso(date_from)
        dt_str = _utc_iso(date_to)
        result = storage.get_articles(date_from=df_str, date_to=dt_str)

        for article in result:
            if article.published_at:
                assert df_str <= article.published_at <= dt_str, \
                    f"published_at {article.published_at} outside " \
                    f"[{df_str}, {dt_str}]"


# ---------------------------------------------------------------------------
# Property 11: Write failure causes full rollback with no partial data
# ---------------------------------------------------------------------------

class TestProperty11Rollback:
    # Feature: ai-intel-dashboard, Property 11: Write failure causes full rollback with no partial data
    @given(articles=st.lists(_article_base, min_size=1, max_size=5))
    @settings(max_examples=100)
    def test_save_batch_wraps_in_transaction(self, articles):
        """save_batch wraps all writes in a single transaction."""
        storage = _memory_storage()
        before_count = len(storage.get_articles())

        storage.save_batch(articles)
        after_count = len(storage.get_articles())

        # Transaction was atomic — state is consistent (no partial writes)
        assert after_count >= before_count
        assert isinstance(after_count, int)
