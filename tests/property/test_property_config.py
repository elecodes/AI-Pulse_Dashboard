"""Property-based tests for ConfigLoader (Properties 13, 14).

# Feature: ai-intel-dashboard, Property 13: Invalid config raises ConfigurationError
# Feature: ai-intel-dashboard, Property 14: AIID_* env vars override YAML config values
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml
from hypothesis import given, settings, strategies as st

from backend.config.config_loader import (
    ConfigLoader,
    ConfigurationError,
    FeedConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp_config(content: str) -> str:
    """Write *content* to a temporary file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Property 13: Invalid or incomplete config raises ConfigurationError
# ---------------------------------------------------------------------------

class TestProperty13InvalidConfig:
    # Feature: ai-intel-dashboard, Property 13: Invalid config raises ConfigurationError
    @given(
        extra=st.dictionaries(
            st.sampled_from(["lookback_hours", "run_interval_minutes"]),
            st.integers(min_value=1, max_value=300),
            max_size=2,
        ),
    )
    @settings(max_examples=100)
    def test_missing_feeds_raises_configuration_error(self, extra):
        config = dict(extra)
        path = _write_tmp_config(yaml.dump(config))
        try:
            with pytest.raises(ConfigurationError):
                ConfigLoader.load(path)
        finally:
            os.unlink(path)

    # Feature: ai-intel-dashboard, Property 13: Invalid config raises ConfigurationError
    @given(
        feeds=st.lists(
            st.builds(
                FeedConfig,
                name=st.text(min_size=1, max_size=20),
                type=st.sampled_from(["rss", "arxiv", "huggingface"]),
                url=st.from_regex(r"https?://[a-z0-9.-]+/\S*",
                                  fullmatch=False).filter(lambda s: len(s) > 0),
                enabled=st.booleans(),
                categories=st.lists(st.text(max_size=10), max_size=3),
            ),
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_invalid_field_type_raises_configuration_error(self, feeds):
        config = {
            "feeds": [f.model_dump() for f in feeds],
            "lookback_hours": "not-an-integer",
        }
        path = _write_tmp_config(yaml.dump(config))
        try:
            with pytest.raises(ConfigurationError):
                ConfigLoader.load(path)
        finally:
            os.unlink(path)

    # Feature: ai-intel-dashboard, Property 13: Invalid config raises ConfigurationError
    @given(
        env_var_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="_",
            ),
            min_size=5, max_size=20,
        ).map(lambda s: "AIID_" + s.upper()),
    )
    @settings(max_examples=100)
    def test_invalid_config_exits_before_scraping(self, env_var_name):
        config = {
            "feeds": [{"name": "t", "type": "rss",
                       "url": "https://example.com/rss"}],
            "lookback_hours": 0,
        }
        path = _write_tmp_config(yaml.dump(config))
        try:
            with patch.dict(os.environ, {env_var_name: "42"}, clear=False):
                with pytest.raises(ConfigurationError):
                    ConfigLoader.load(path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Property 14: AIID_* environment variables override YAML config values
# ---------------------------------------------------------------------------

class TestProperty14EnvOverrides:
    # Feature: ai-intel-dashboard, Property 14: AIID_* env vars override YAML config values
    @given(
        yaml_value=st.integers(min_value=1, max_value=100),
        env_value=st.integers(min_value=101, max_value=200),
    )
    @settings(max_examples=100)
    def test_aiid_override_takes_precedence(self, yaml_value, env_value):
        config = {
            "feeds": [{"name": "t", "type": "rss",
                       "url": "https://example.com/rss"}],
            "lookback_hours": yaml_value,
        }
        path = _write_tmp_config(yaml.dump(config))
        try:
            with patch.dict(os.environ,
                           {"AIID_LOOKBACK_HOURS": str(env_value)},
                           clear=True):
                result = ConfigLoader.load(path)
            assert result.lookback_hours == env_value
        finally:
            os.unlink(path)

    # Feature: ai-intel-dashboard, Property 14: AIID_* env vars override YAML config values
    @given(
        yaml_val=st.integers(min_value=10, max_value=120),
        env_val=st.integers(min_value=5, max_value=15),
    )
    @settings(max_examples=100)
    def test_multiple_config_fields_overridable(self, yaml_val, env_val):
        config = {
            "feeds": [{"name": "t", "type": "rss",
                       "url": "https://example.com/rss"}],
            "lookback_hours": yaml_val,
            "run_interval_minutes": yaml_val,
        }
        path = _write_tmp_config(yaml.dump(config))
        try:
            overrides = {
                "AIID_LOOKBACK_HOURS": str(env_val),
                "AIID_RUN_INTERVAL_MINUTES": str(yaml_val),
            }
            with patch.dict(os.environ, overrides, clear=True):
                result = ConfigLoader.load(path)
            assert result.lookback_hours == env_val
            assert result.run_interval_minutes == yaml_val
        finally:
            os.unlink(path)

    # Feature: ai-intel-dashboard, Property 14: AIID_* env vars override YAML config values
    @given(yaml_val=st.integers(min_value=1, max_value=500))
    @settings(max_examples=100)
    def test_override_with_valid_value_works(self, yaml_val):
        config = {
            "feeds": [{"name": "t", "type": "rss",
                       "url": "https://example.com/rss"}],
            "lookback_hours": yaml_val,
        }
        path = _write_tmp_config(yaml.dump(config))
        try:
            new_val = yaml_val + 100
            with patch.dict(os.environ,
                           {"AIID_LOOKBACK_HOURS": str(new_val)},
                           clear=False):
                result = ConfigLoader.load(path)
            assert result.lookback_hours == new_val
        finally:
            os.unlink(path)
