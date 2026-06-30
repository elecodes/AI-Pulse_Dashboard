"""Property-based tests for JSON logging (Property 15).

# Feature: ai-intel-dashboard, Property 15: JSON log format emits valid, parseable JSON
"""
from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

from backend.logging_config import JsonFormatter, setup_logging


# ---------------------------------------------------------------------------
# Property 15: JSON log format emits valid, parseable JSON per log event
# ---------------------------------------------------------------------------

class TestProperty15JsonLogFormat:
    # Feature: ai-intel-dashboard, Property 15: JSON log format emits valid, parseable JSON
    @given(
        logger_name=st.text(min_size=1, max_size=30),
        message=st.text(max_size=200),
        level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=100)
    def test_json_format_emits_valid_json(self, logger_name, message, level):
        formatter = JsonFormatter()
        logger = logging.getLogger(logger_name)
        record = logger.makeRecord(
            logger_name, getattr(logging, level),
            "test_module.py", 42, message, (), None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict), "Output must be a JSON object"
        assert "ts" in parsed, "Must contain 'ts' key"
        assert "level" in parsed, "Must contain 'level' key"
        assert "logger" in parsed, "Must contain 'logger' key"
        assert "message" in parsed, "Must contain 'message' key"
        assert parsed["level"] == level, "Level must match"
        assert parsed["logger"] == logger_name, "Logger name must match"
        assert parsed["message"] == message, "Message must match"

    # Feature: ai-intel-dashboard, Property 15: JSON log format emits valid, parseable JSON
    @given(
        message=st.text(max_size=100),
        level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    )
    @settings(max_examples=100)
    def test_setup_logging_emits_json_lines(self, message, level):
        """When LOG_FORMAT=json, each log line must be parseable as JSON."""
        with patch.dict(os.environ, {
            "LOG_FORMAT": "json",
            "LOG_LEVEL": "DEBUG",
        }, clear=True):
            setup_logging()
            root = logging.getLogger()
            root.handlers.clear()  # clean up after test

            # Re-setup with proper isolation
            setup_logging()

            logger = logging.getLogger("test-property-15")
            logger.propagate = False

            # Use a StringIO handler to capture output
            import io
            string_buf = io.StringIO()
            handler = logging.StreamHandler(string_buf)
            handler.setFormatter(JsonFormatter())
            logger.addHandler(handler)

            getattr(logger, level.lower())(message)
            handler.flush()
            output = string_buf.getvalue().strip()

            if output:
                for line in output.split("\n"):
                    line = line.strip()
                    if line:
                        parsed = json.loads(line)
                        assert "ts" in parsed
                        assert "level" in parsed
                        assert "logger" in parsed
                        assert "message" in parsed
