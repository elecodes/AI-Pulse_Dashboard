"""Config loader for the AI Intelligence Dashboard.

Loads feed and application configuration from a YAML file, merges
``AIID_*`` environment variable overrides, and validates the result
into a typed ``AppConfig`` object via pydantic.

Usage::

    from backend.config.config_loader import ConfigLoader, ConfigurationError

    try:
        config = ConfigLoader.load("config/feeds.yaml")
    except ConfigurationError as exc:
        # Already logged at ERROR level; caller should exit(1).
        raise
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class ConfigurationError(Exception):
    """Raised when the application configuration is missing, invalid, or
    cannot be parsed.  Callers (e.g. the CLI entry point) should log at
    ERROR level and exit with a non-zero status code.
    """


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FeedConfig(BaseModel):
    """Configuration for a single external feed source."""

    name: str
    type: Literal["rss", "arxiv", "huggingface"]
    url: str
    enabled: bool = True
    categories: list[str] = []  # used by the arxiv scraper


class AppConfig(BaseModel):
    """Top-level application configuration.

    All fields have sensible defaults except ``feeds``, which is required
    and must contain at least one entry.
    """

    feeds: list[FeedConfig]
    lookback_hours: int = Field(default=48, ge=1)
    run_interval_minutes: int = Field(default=60, ge=1)
    pipeline_timeout_seconds: int = Field(default=300, ge=10)
    db_path: str = "data/articles.db"
    json_export_path: str = "data/articles.json"
    llm_provider: Literal["openai", "anthropic"] | None = None
    llm_batch_size: int = Field(default=20, ge=1)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

# Mapping from AIID_<KEY> → AppConfig field name (lowercase).
# Only scalar top-level fields can be overridden via environment variables.
_OVERRIDABLE_FIELDS = {
    field_name
    for field_name in AppConfig.model_fields
    if field_name != "feeds"
}


class ConfigLoader:
    """Loads and validates ``AppConfig`` from a YAML file.

    Environment variable overrides (``AIID_<SETTING_NAME>``) are merged
    after the YAML is parsed but before pydantic validation runs.  This
    means an env var can correct a value that would otherwise fail
    validation, but a completely absent ``feeds`` key still raises
    ``ConfigurationError``.
    """

    @classmethod
    def load(cls, path: str) -> AppConfig:
        """Load configuration from *path*, merge env overrides, and validate.

        Parameters
        ----------
        path:
            File-system path to the YAML configuration file.

        Returns
        -------
        AppConfig
            Fully validated configuration object.

        Raises
        ------
        ConfigurationError
            On file-not-found, YAML parse error, or pydantic validation
            failure (missing required field, invalid value, etc.).
        """
        raw_data = cls._load_yaml(path)
        cls._apply_env_overrides(raw_data)
        return cls._validate(raw_data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @classmethod
    def _load_yaml(cls, path: str) -> dict:
        """Read and parse the YAML file at *path*.

        Raises
        ------
        ConfigurationError
            If the file does not exist or cannot be parsed as YAML.
        """
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            msg = f"Configuration file not found: {path!r}"
            logger.error(msg)
            raise ConfigurationError(msg) from None
        except yaml.YAMLError as exc:
            msg = f"Failed to parse YAML configuration at {path!r}: {exc}"
            logger.error(msg)
            raise ConfigurationError(msg) from exc

        if not isinstance(data, dict):
            msg = (
                f"Configuration file {path!r} must contain a YAML mapping at "
                f"the top level, got {type(data).__name__!r}."
            )
            logger.error(msg)
            raise ConfigurationError(msg)

        return data

    @classmethod
    def _apply_env_overrides(cls, data: dict) -> None:
        """Mutate *data* in-place with values from ``AIID_*`` env vars.

        Only scalar top-level fields (i.e. everything except ``feeds``) are
        eligible for override.  Unknown ``AIID_*`` keys are silently ignored
        so that mis-typed variable names don't break startup.

        The env var value is always a string; pydantic coerces it to the
        correct type during validation.
        """
        prefix = "AIID_"
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            field_name = key[len(prefix):].lower()
            if field_name in _OVERRIDABLE_FIELDS:
                data[field_name] = value

    @classmethod
    def _validate(cls, data: dict) -> AppConfig:
        """Run pydantic validation over *data*.

        Raises
        ------
        ConfigurationError
            On any pydantic ``ValidationError`` (missing required field,
            wrong type, constraint violation, etc.).
        """
        try:
            return AppConfig(**data)
        except ValidationError as exc:
            # Build a human-readable summary of every error pydantic found.
            error_lines = []
            for error in exc.errors():
                loc = " -> ".join(str(l) for l in error["loc"])
                error_lines.append(f"  [{loc}] {error['msg']}")
            msg = (
                "Invalid configuration:\n" + "\n".join(error_lines)
            )
            logger.error(msg)
            raise ConfigurationError(msg) from exc
        except TypeError as exc:
            msg = f"Unexpected configuration structure: {exc}"
            logger.error(msg)
            raise ConfigurationError(msg) from exc
