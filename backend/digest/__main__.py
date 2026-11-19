"""CLI entry point for the email digest service.

Usage:
    python -m backend.digest [--dry-run] [--days 4] [--recipient user@gmail.com]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from backend.config.config_loader import ConfigLoader
from backend.digest.newsletter import DigestCollector, DigestFormatter, GmailSender
from backend.logging_config import setup_logging
from backend.storage.storage_layer import StorageLayer


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.digest",
        description="Generate and dispatch AI & Agents newsletter digest via Gmail.",
    )
    parser.add_argument(
        "--config",
        default="config/feeds.yaml",
        help="Path to YAML feeds config (default: config/feeds.yaml)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=4,
        help="Lookback window in days (default: 4, covering Mon-Thu or Thu-Mon)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of articles to include in digest (default: 20)",
    )
    parser.add_argument(
        "--recipient",
        help="Target email address (overrides GMAIL_TO)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print digest without sending email via SMTP.",
    )

    args = parser.parse_args()
    load_dotenv()
    setup_logging()

    try:
        config = ConfigLoader.load(args.config)
        storage = StorageLayer(config.db_path)
        storage.init_db()

        collector = DigestCollector(storage)
        articles = collector.collect(days=args.days, limit=args.limit)

        text_body = DigestFormatter.format_text(articles)
        html_body = DigestFormatter.format_html(articles)

        if args.dry_run:
            print("\n=== DRY RUN: DIGEST PREVIEW ===\n")
            print(text_body)
            print("===============================\n")

        today_name = datetime.now(tz=timezone.utc).strftime("%A, %b %d")
        subject = f"🤖 AI & Agents Highlights — {today_name} ({len(articles)} stories)"

        sender = GmailSender(default_recipient=args.recipient)
        sender.send(
            subject=subject,
            text_content=text_body,
            html_content=html_body,
            recipient=args.recipient,
            dry_run=args.dry_run,
        )

        print(f"Digest ready ({len(articles)} articles). Status: {'Dry-run OK' if args.dry_run else 'Sent'}")
        return 0

    except Exception as exc:
        print(f"Error executing digest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
