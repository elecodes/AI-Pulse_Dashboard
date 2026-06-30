"""Logging configuration for the AI Intelligence Dashboard.

Provides:
- ``JsonFormatter``: emits one JSON object per log record with keys
  ``ts``, ``level``, ``logger``, ``message``, optional ``exc``, and any
  extra fields stored under ``record.__dict__["extra"]``.
- ``setup_logging()``: reads ``LOG_FORMAT``, ``LOG_LEVEL``, and
  ``LOG_FILE`` environment variables and configures the root logger.

Requirements: 9.1, 9.2, 9.4
"""

from __future__ import annotations

import json
import logging
import os
import sys


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Minimum keys emitted:
        ``ts``      – UTC timestamp in ``YYYY-MM-DDTHH:MM:SSZ`` format
        ``level``   – log level name (e.g. ``"INFO"``)
        ``logger``  – logger name
        ``message`` – the formatted log message

    Optional keys:
        ``exc``  – formatted exception traceback (present only when
                   ``record.exc_info`` is set)
        any key from ``record.__dict__.get("extra", {})``
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        extra = record.__dict__.get("extra", {})
        if extra:
            payload.update(extra)

        return json.dumps(payload)


def setup_logging() -> None:
    """Configure the root logger from environment variables.

    Environment variables read:
        LOG_FORMAT  – when set to ``"json"`` the ``JsonFormatter`` is
                      used; any other value (or unset) falls back to
                      Python's default ``logging.Formatter``.
        LOG_LEVEL   – standard level name (e.g. ``"DEBUG"``, ``"WARNING"``).
                      Defaults to ``"INFO"`` when not set or unrecognised.
        LOG_FILE    – path to a log file.  When set, a ``FileHandler``
                      pointing to that path is added in addition to the
                      stdout ``StreamHandler``.

    A ``StreamHandler`` writing to *stdout* is always attached.  Both
    handlers share the same formatter and the same level as the root
    logger.
    """
    log_format = os.environ.get("LOG_FORMAT", "").strip().lower()
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    log_file = os.environ.get("LOG_FILE", "").strip()

    # Resolve the numeric level; fall back to INFO for unknown names.
    numeric_level = getattr(logging, log_level_name, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Choose formatter.
    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )

    root_logger = logging.getLogger()

    # Remove any handlers already attached (idempotent re-configuration).
    root_logger.handlers.clear()

    root_logger.setLevel(numeric_level)

    # stdout handler — always present.
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(numeric_level)
    root_logger.addHandler(stdout_handler)

    # Optional file handler.
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        root_logger.addHandler(file_handler)
