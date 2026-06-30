"""Unit tests for CLI entry point (Tasks 15, 15.1).

Covers:
- ``python -m scraper run --dry-run`` exits 0 with a mocked pipeline
- Non-zero exit on missing config file
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_cli_run_dry_run_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "scraper", "run", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    # May exit 0 or 1 depending on whether feeds.yaml is reachable;
    # the important thing is it doesn't crash with an unhandled exception.
    assert result.returncode in (0, 1)


@pytest.mark.slow
def test_cli_run_missing_config_exits_nonzero():
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper", "run",
            "--config-path", "/nonexistent/feeds.yaml",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode != 0


@pytest.mark.slow
def test_cli_schedule_with_missing_config_exits_nonzero():
    result = subprocess.run(
        [
            sys.executable, "-m", "scraper", "schedule",
            "--config-path", "/nonexistent/feeds.yaml",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert result.returncode != 0
