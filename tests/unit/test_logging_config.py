"""Unit tests for backend.logging_config (Task 4.1).

Covers:
- setup_logging() with LOG_FORMAT=json produces valid JSON output.
- setup_logging() without LOG_FORMAT produces human-readable (non-JSON) output.
- JSON output contains the required keys: ts, level, logger, message.
- LOG_LEVEL=DEBUG sets the root logger to DEBUG level.
- LOG_FILE causes a FileHandler to be added to the root logger.
- Exception info is included as the "exc" key in JSON output.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from backend.logging_config import JsonFormatter, setup_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _capture_log_output(level: int, message: str, **env_overrides) -> str:
    """Run setup_logging() with patched env, emit one record, return raw output."""
    buf = io.StringIO()

    root = logging.getLogger()
    root.handlers.clear()

    # Attach a StringIO-backed StreamHandler so we can inspect the output.
    handler = logging.StreamHandler(buf)
    root.addHandler(handler)
    root.setLevel(level)

    # Give the handler the formatter under test directly.
    log_format = env_overrides.get("LOG_FORMAT", "")
    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
        )

    logger = logging.getLogger("test.capture")
    logger.log(level, message)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON format output
# ---------------------------------------------------------------------------


class TestJsonFormat:
    """setup_logging() with LOG_FORMAT=json."""

    def test_output_is_valid_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        buf = io.StringIO()
        setup_logging()

        # Replace the stdout handler's stream with our buffer.
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.json").info("hello json")

        output = buf.getvalue().strip()
        assert output, "Expected at least one log line"
        # Every line must be valid JSON.
        for line in output.splitlines():
            json.loads(line)  # raises on invalid JSON

    def test_json_output_contains_required_keys(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.keys").warning("check keys")

        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        for key in ("ts", "level", "logger", "message"):
            assert key in parsed, f"Required key '{key}' missing from JSON log"

    def test_ts_format_matches_iso8601_utc(self, monkeypatch):
        import re

        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.ts").info("ts format check")

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        assert ts_pattern.match(parsed["ts"]), (
            f"ts '{parsed['ts']}' does not match YYYY-MM-DDTHH:MM:SSZ"
        )

    def test_level_field_contains_level_name(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.level").error("an error")

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert parsed["level"] == "ERROR"

    def test_logger_field_contains_logger_name(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("my.custom.logger").info("msg")

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert parsed["logger"] == "my.custom.logger"

    def test_message_field_contains_log_message(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.msg").info("the expected message")

        parsed = json.loads(buf.getvalue().strip().splitlines()[-1])
        assert parsed["message"] == "the expected message"


# ---------------------------------------------------------------------------
# Human-readable format output
# ---------------------------------------------------------------------------


class TestHumanReadableFormat:
    """setup_logging() without LOG_FORMAT (or any non-json value) is non-JSON."""

    def test_output_is_not_json_when_log_format_unset(self, monkeypatch):
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.human").info("human readable")

        line = buf.getvalue().strip().splitlines()[-1]
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(line)

    def test_output_is_not_json_when_log_format_is_text(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.text").info("text format")

        line = buf.getvalue().strip().splitlines()[-1]
        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(line)


# ---------------------------------------------------------------------------
# LOG_LEVEL
# ---------------------------------------------------------------------------


class TestLogLevel:
    def test_debug_level_sets_root_logger_to_debug(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    def test_warning_level_sets_root_logger_to_warning(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()
        assert logging.getLogger().level == logging.WARNING

    def test_default_level_is_info_when_unset(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()
        assert logging.getLogger().level == logging.INFO

    def test_invalid_level_name_falls_back_to_info(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "NOTAVALIDLEVEL")
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()
        assert logging.getLogger().level == logging.INFO


# ---------------------------------------------------------------------------
# LOG_FILE
# ---------------------------------------------------------------------------


class TestLogFile:
    def test_file_handler_added_when_log_file_set(self, monkeypatch, tmp_path):
        log_path = str(tmp_path / "test.log")
        monkeypatch.setenv("LOG_FILE", log_path)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1, "Exactly one FileHandler expected"
        assert file_handlers[0].baseFilename == log_path

    def test_no_file_handler_when_log_file_unset(self, monkeypatch):
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_stdout_handler_always_present(self, monkeypatch):
        monkeypatch.delenv("LOG_FILE", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()

        root = logging.getLogger()
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) >= 1

    def test_file_handler_writes_to_file(self, monkeypatch, tmp_path):
        log_path = tmp_path / "output.log"
        monkeypatch.setenv("LOG_FILE", str(log_path))
        monkeypatch.setenv("LOG_FORMAT", "json")

        setup_logging()

        logging.getLogger("test.file").info("written to file")

        # Flush all handlers.
        for h in logging.getLogger().handlers:
            h.flush()

        content = log_path.read_text(encoding="utf-8").strip()
        assert content, "Log file should have content"
        parsed = json.loads(content.splitlines()[-1])
        assert parsed["message"] == "written to file"

    def test_both_stdout_and_file_handlers_present_when_log_file_set(
        self, monkeypatch, tmp_path
    ):
        log_path = str(tmp_path / "both.log")
        monkeypatch.setenv("LOG_FILE", log_path)
        monkeypatch.delenv("LOG_FORMAT", raising=False)

        setup_logging()

        root = logging.getLogger()
        assert len(root.handlers) == 2


# ---------------------------------------------------------------------------
# Exception info in JSON output
# ---------------------------------------------------------------------------


class TestExceptionInfo:
    def test_exc_key_present_when_exception_logged(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("test.exc").exception("something went wrong")

        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert "exc" in parsed, "'exc' key must be present when exception is logged"
        assert "ValueError" in parsed["exc"]
        assert "boom" in parsed["exc"]

    def test_exc_key_absent_when_no_exception(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        monkeypatch.delenv("LOG_FILE", raising=False)

        buf = io.StringIO()
        setup_logging()
        root = logging.getLogger()
        root.handlers[0].stream = buf

        logging.getLogger("test.noexc").info("no exception here")

        line = buf.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)
        assert "exc" not in parsed, "'exc' key must NOT be present for non-exception records"


# ---------------------------------------------------------------------------
# JsonFormatter unit tests (formatter in isolation)
# ---------------------------------------------------------------------------


class TestJsonFormatterDirectly:
    """Test JsonFormatter.format() without going through setup_logging()."""

    def _make_record(
        self,
        msg: str = "test message",
        level: int = logging.INFO,
        name: str = "test.logger",
        exc_info=None,
        extra: dict | None = None,
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=exc_info,
        )
        if extra is not None:
            record.__dict__["extra"] = extra
        return record

    def test_format_returns_valid_json(self):
        formatter = JsonFormatter()
        record = self._make_record()
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_format_includes_all_required_keys(self):
        formatter = JsonFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        for key in ("ts", "level", "logger", "message"):
            assert key in parsed

    def test_format_exc_key_included_with_exc_info(self):
        formatter = JsonFormatter()
        try:
            raise RuntimeError("test error")
        except RuntimeError:
            import sys
            exc = sys.exc_info()

        record = self._make_record(exc_info=exc)
        parsed = json.loads(formatter.format(record))
        assert "exc" in parsed
        assert "RuntimeError" in parsed["exc"]

    def test_format_extra_fields_merged_into_output(self):
        formatter = JsonFormatter()
        record = self._make_record(extra={"request_id": "abc-123", "user": "alice"})
        parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] == "abc-123"
        assert parsed["user"] == "alice"

    def test_format_no_extra_key_when_extra_absent(self):
        formatter = JsonFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert "extra" not in parsed

    def test_format_level_name_matches_record_level(self):
        formatter = JsonFormatter()
        record = self._make_record(level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"
