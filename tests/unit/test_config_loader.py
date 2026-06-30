"""Unit tests for backend.config.config_loader (Tasks 3.1 & 3.2).

Covers:
- Successful load from a valid YAML file.
- ConfigurationError raised when the file is missing.
- ConfigurationError raised on invalid (non-parseable) YAML.
- AIID_* environment variables override YAML values.
- ConfigurationError raised when a required field (feeds) is absent.
- FeedConfig fields are parsed correctly (including the optional
  ``categories`` field used by the arxiv scraper).
- AppConfig defaults are applied when optional fields are omitted.
- env override values are coerced to the correct type (e.g. int).
"""

from __future__ import annotations

import os
import textwrap

import pytest

from backend.config.config_loader import AppConfig, ConfigLoader, ConfigurationError, FeedConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def valid_yaml(tmp_path) -> str:
    """Write a minimal but complete feeds.yaml and return its path."""
    content = textwrap.dedent("""\
        lookback_hours: 24
        run_interval_minutes: 30
        pipeline_timeout_seconds: 120
        db_path: data/test.db
        json_export_path: data/test.json

        feeds:
          - name: techcrunch-ai
            type: rss
            url: https://techcrunch.com/category/artificial-intelligence/feed/
            enabled: true

          - name: arxiv-cs-ai
            type: arxiv
            url: http://export.arxiv.org/api/query
            categories: [cs.AI, cs.LG]
            enabled: true

          - name: huggingface-trending
            type: huggingface
            url: https://huggingface.co/api/models
            enabled: false
    """)
    config_file = tmp_path / "feeds.yaml"
    config_file.write_text(content, encoding="utf-8")
    return str(config_file)


@pytest.fixture()
def feeds_only_yaml(tmp_path) -> str:
    """Write a YAML that has only the required 'feeds' key."""
    content = textwrap.dedent("""\
        feeds:
          - name: test-rss
            type: rss
            url: https://example.com/feed
    """)
    config_file = tmp_path / "feeds_only.yaml"
    config_file.write_text(content, encoding="utf-8")
    return str(config_file)


# ---------------------------------------------------------------------------
# Successful load
# ---------------------------------------------------------------------------


class TestSuccessfulLoad:
    def test_returns_app_config_instance(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        assert isinstance(config, AppConfig)

    def test_scalar_fields_are_loaded(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        assert config.lookback_hours == 24
        assert config.run_interval_minutes == 30
        assert config.pipeline_timeout_seconds == 120
        assert config.db_path == "data/test.db"
        assert config.json_export_path == "data/test.json"

    def test_feeds_list_length(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        assert len(config.feeds) == 3

    def test_rss_feed_fields(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        rss_feed = config.feeds[0]
        assert isinstance(rss_feed, FeedConfig)
        assert rss_feed.name == "techcrunch-ai"
        assert rss_feed.type == "rss"
        assert rss_feed.url == "https://techcrunch.com/category/artificial-intelligence/feed/"
        assert rss_feed.enabled is True
        assert rss_feed.categories == []

    def test_arxiv_feed_has_categories(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        arxiv_feed = config.feeds[1]
        assert arxiv_feed.type == "arxiv"
        assert arxiv_feed.categories == ["cs.AI", "cs.LG"]

    def test_disabled_feed_is_loaded(self, valid_yaml):
        config = ConfigLoader.load(valid_yaml)
        hf_feed = config.feeds[2]
        assert hf_feed.enabled is False

    def test_defaults_applied_when_optional_fields_omitted(self, feeds_only_yaml):
        """When optional AppConfig fields are absent, pydantic defaults kick in."""
        config = ConfigLoader.load(feeds_only_yaml)
        assert config.lookback_hours == 48
        assert config.run_interval_minutes == 60
        assert config.pipeline_timeout_seconds == 300
        assert config.db_path == "data/articles.db"
        assert config.json_export_path == "data/articles.json"
        assert config.llm_provider is None
        assert config.llm_batch_size == 20


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_raises_configuration_error(self, tmp_path):
        missing = str(tmp_path / "does_not_exist.yaml")
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigLoader.load(missing)
        assert "not found" in str(exc_info.value).lower()

    def test_error_message_contains_path(self, tmp_path):
        missing = str(tmp_path / "missing_config.yaml")
        with pytest.raises(ConfigurationError, match="missing_config.yaml"):
            ConfigLoader.load(missing)


# ---------------------------------------------------------------------------
# Invalid YAML
# ---------------------------------------------------------------------------


class TestInvalidYaml:
    def test_raises_configuration_error_on_bad_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("feeds: [\nunclosed bracket", encoding="utf-8")
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(bad_yaml))

    def test_raises_configuration_error_on_non_mapping_yaml(self, tmp_path):
        """Top-level YAML must be a mapping, not a list or scalar."""
        bad_yaml = tmp_path / "list.yaml"
        bad_yaml.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(bad_yaml))


# ---------------------------------------------------------------------------
# AIID_* environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvOverrides:
    def test_aiid_lookback_hours_overrides_yaml(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_LOOKBACK_HOURS", "72")
        config = ConfigLoader.load(valid_yaml)
        assert config.lookback_hours == 72

    def test_aiid_db_path_overrides_yaml(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_DB_PATH", "/mnt/data/articles.db")
        config = ConfigLoader.load(valid_yaml)
        assert config.db_path == "/mnt/data/articles.db"

    def test_aiid_run_interval_overrides_yaml(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_RUN_INTERVAL_MINUTES", "15")
        config = ConfigLoader.load(valid_yaml)
        assert config.run_interval_minutes == 15

    def test_aiid_pipeline_timeout_overrides_yaml(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_PIPELINE_TIMEOUT_SECONDS", "600")
        config = ConfigLoader.load(valid_yaml)
        assert config.pipeline_timeout_seconds == 600

    def test_aiid_json_export_path_overrides_yaml(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_JSON_EXPORT_PATH", "/tmp/export.json")
        config = ConfigLoader.load(valid_yaml)
        assert config.json_export_path == "/tmp/export.json"

    def test_unknown_aiid_prefix_is_ignored(self, valid_yaml, monkeypatch):
        """Unrecognised AIID_* keys must not raise."""
        monkeypatch.setenv("AIID_UNKNOWN_SETTING_XYZ", "value")
        config = ConfigLoader.load(valid_yaml)  # must not raise
        assert isinstance(config, AppConfig)

    def test_env_override_takes_precedence_over_yaml(self, valid_yaml, monkeypatch):
        """YAML says lookback_hours=24; env says 99 — env must win."""
        monkeypatch.setenv("AIID_LOOKBACK_HOURS", "99")
        config = ConfigLoader.load(valid_yaml)
        assert config.lookback_hours == 99

    def test_multiple_overrides_applied_simultaneously(self, valid_yaml, monkeypatch):
        monkeypatch.setenv("AIID_LOOKBACK_HOURS", "6")
        monkeypatch.setenv("AIID_RUN_INTERVAL_MINUTES", "5")
        config = ConfigLoader.load(valid_yaml)
        assert config.lookback_hours == 6
        assert config.run_interval_minutes == 5


# ---------------------------------------------------------------------------
# Missing required field
# ---------------------------------------------------------------------------


class TestMissingRequiredField:
    def test_raises_configuration_error_when_feeds_missing(self, tmp_path):
        """'feeds' is required; its absence must raise ConfigurationError."""
        no_feeds = tmp_path / "no_feeds.yaml"
        no_feeds.write_text(
            "lookback_hours: 48\nrun_interval_minutes: 60\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(no_feeds))

    def test_raises_configuration_error_when_feed_missing_name(self, tmp_path):
        """A feed entry without 'name' must fail validation."""
        bad_feed = tmp_path / "bad_feed.yaml"
        bad_feed.write_text(
            textwrap.dedent("""\
                feeds:
                  - type: rss
                    url: https://example.com/feed
            """),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(bad_feed))

    def test_raises_configuration_error_when_feed_missing_url(self, tmp_path):
        bad_feed = tmp_path / "no_url.yaml"
        bad_feed.write_text(
            textwrap.dedent("""\
                feeds:
                  - name: test
                    type: rss
            """),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(bad_feed))

    def test_raises_configuration_error_on_invalid_feed_type(self, tmp_path):
        """Feed 'type' must be one of rss | arxiv | huggingface."""
        bad_type = tmp_path / "bad_type.yaml"
        bad_type.write_text(
            textwrap.dedent("""\
                feeds:
                  - name: test
                    type: atom
                    url: https://example.com/feed
            """),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError):
            ConfigLoader.load(str(bad_type))

    def test_error_message_is_descriptive(self, tmp_path):
        no_feeds = tmp_path / "no_feeds2.yaml"
        no_feeds.write_text("lookback_hours: 48\n", encoding="utf-8")
        with pytest.raises(ConfigurationError) as exc_info:
            ConfigLoader.load(str(no_feeds))
        # Message should mention the invalid config
        assert "Invalid configuration" in str(exc_info.value)
