"""CLI entry point for the AI Intelligence Dashboard.

Usage::

    python -m scraper run              # one-shot pipeline
    python -m scraper run --dry-run    # preview without writing
    python -m scraper schedule         # start the blocking scheduler

Both subcommands accept ``--config-path`` to point at a non-default
configuration file.
"""

from __future__ import annotations

import argparse
import logging
import sys

from backend.config.config_loader import ConfigLoader, ConfigurationError
from backend.logging_config import setup_logging
from backend.pipeline.pipeline import Pipeline
from backend.pipeline.scheduler import PipelineScheduler
from backend.storage.storage_layer import StorageLayer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Python version guard
# ---------------------------------------------------------------------------


def check_python_version() -> None:
    """Exit with a descriptive error if Python < 3.11."""
    if sys.version_info < (3, 11):
        print(
            "ERROR: AI Intelligence Dashboard requires Python >= 3.11, "
            f"but found {sys.version_info.major}.{sys.version_info.minor}.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Config loader shortcut
# ---------------------------------------------------------------------------


def _load_config(path: str):
    """Load and return an ``AppConfig``, exiting on failure."""
    try:
        return ConfigLoader.load(path)
    except ConfigurationError:
        logger.error("Exiting due to configuration error.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> None:
    """Execute a single pipeline run."""
    config = _load_config(args.config_path)
    storage = StorageLayer(config.db_path)
    storage.init_db()

    pipeline = Pipeline(config, storage)
    result = pipeline.run(dry_run=args.dry_run)

    logger.info(
        "Run %s — status=%s feeds_succeeded=%d/%d "
        "fetched=%d inserted=%d deduped=%d discarded=%d "
        "duration=%.2fs",
        result.run_id,
        result.status,
        result.feeds_succeeded,
        result.feeds_configured,
        result.raw_records_fetched,
        result.articles_inserted,
        result.articles_deduped,
        result.articles_discarded,
        result.duration_seconds,
    )

    if result.status == "failure":
        sys.exit(1)


def cmd_schedule(args: argparse.Namespace) -> None:
    """Start the blocking scheduler."""
    config = _load_config(args.config_path)
    storage = StorageLayer(config.db_path)
    storage.init_db()

    pipeline = Pipeline(config, storage)

    scheduler = PipelineScheduler(config, pipeline)
    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.stop()
        sys.exit(0)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="AI Intelligence Dashboard — scraper pipeline CLI",
    )

    parser.add_argument(
        "--config-path",
        default="config/feeds.yaml",
        help="Path to the YAML configuration file "
             "(default: config/feeds.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_parser = subparsers.add_parser(
        "run", help="Execute a single pipeline run"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and normalise but do not write to storage",
    )
    run_parser.set_defaults(func=cmd_run)

    # schedule
    schedule_parser = subparsers.add_parser(
        "schedule", help="Start the blocking scheduler"
    )
    schedule_parser.set_defaults(func=cmd_schedule)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Top-level entry point for ``python -m scraper``."""
    check_python_version()
    setup_logging()

    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as exc:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
