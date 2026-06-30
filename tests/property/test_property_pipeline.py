"""Property-based test for Pipeline dry-run (Property 12).

# Feature: ai-intel-dashboard, Property 12: Dry-run flag prevents all StorageLayer writes
"""
from __future__ import annotations

from unittest.mock import MagicMock

from hypothesis import given, settings, strategies as st

from backend.config.config_loader import AppConfig, FeedConfig
from backend.pipeline.pipeline import Pipeline
from backend.storage.storage_layer import StorageLayer


# ---------------------------------------------------------------------------
# Strategy for generating minimal AppConfig instances
# ---------------------------------------------------------------------------

_feed_config_strategy = st.builds(
    FeedConfig,
    name=st.text(min_size=1, max_size=20),
    type=st.sampled_from(["rss", "arxiv", "huggingface"]),
    url=st.from_regex(r"https?://[a-z0-9.-]+/\S*", fullmatch=False).filter(
        lambda s: len(s) > 0
    ),
    enabled=st.just(True),
    categories=st.lists(st.text(max_size=10), max_size=3),
)

_app_config_strategy = st.builds(
    AppConfig,
    feeds=st.lists(_feed_config_strategy, min_size=1, max_size=3),
    lookback_hours=st.integers(min_value=1, max_value=168),
    run_interval_minutes=st.integers(min_value=1, max_value=1440),
    pipeline_timeout_seconds=st.integers(min_value=10, max_value=600),
    db_path=st.just(":memory:"),
    json_export_path=st.just("/dev/null/articles.json"),
)


class TestProperty12DryRun:
    # Feature: ai-intel-dashboard, Property 12: Dry-run flag prevents all StorageLayer writes
    @given(config=_app_config_strategy)
    @settings(max_examples=50)
    def test_dry_run_does_not_write_to_storage(self, config):
        """With dry_run=True, no articles should be persisted."""
        storage = StorageLayer(":memory:")
        storage.init_db()

        pipeline = Pipeline(config, storage)

        pipeline._scrapers = [
            MagicMock(fetch=MagicMock(return_value=[]), source_name=f"mock-{i}")
            for i in range(len(config.feeds))
        ]

        before = storage.get_articles()
        result = pipeline.run(dry_run=True)
        after = storage.get_articles()

        assert before == after
        assert result.status != "failure"
