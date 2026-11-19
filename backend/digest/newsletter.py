"""Digest generation and email dispatch for AI & Agents highlights.

Extracts top/recent articles from SQLite, formats a clean responsive HTML/text
email digest, and sends it via Gmail SMTP.
"""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from dotenv import load_dotenv

from backend.models.article import Article
from backend.storage.storage_layer import StorageLayer

logger = logging.getLogger(__name__)


class DigestCollector:
    """Collects highlighted articles from storage for the digest."""

    def __init__(self, storage: StorageLayer) -> None:
        self._storage = storage

    def collect(
        self,
        days: int = 4,
        topic_keywords: list[str] | None = None,
        limit: int = 25,
    ) -> list[Article]:
        """Fetch highlighted articles published within the last `days`.

        Prioritizes agent and AI topics if keywords are provided.
        """
        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff_dt.isoformat()

        keywords = topic_keywords or ["agent", "agents", "llm", "ai", "model"]
        query_str = " OR ".join(keywords)

        try:
            articles = self._storage.get_articles(
                date_from=cutoff_str,
                q=query_str,
                limit=limit,
            )
        except Exception as exc:
            logger.warning("FTS query for digest failed (%s); falling back to all recent articles", exc)
            articles = self._storage.get_articles(
                date_from=cutoff_str,
                limit=limit,
            )

        if not articles:
            # If no matches with keyword query, return most recent overall
            articles = self._storage.get_articles(
                date_from=cutoff_str,
                limit=limit,
            )

        return articles


class DigestFormatter:
    """Formats a list of articles into text and HTML email content."""

    @staticmethod
    def format_text(articles: list[Article]) -> str:
        """Format articles as human-readable plain text."""
        lines = [
            "AI & AGENTS - HIGHLIGHTS DIGEST",
            "================================",
            f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total Highlights: {len(articles)}",
            "",
        ]

        if not articles:
            lines.append("No new highlighted articles found for this period.")
            return "\n".join(lines)

        for idx, art in enumerate(articles, start=1):
            category = f"[{art.category}] " if art.category else ""
            source = f"({art.source})" if art.source else ""
            lines.append(f"{idx}. {category}{art.title} {source}")
            lines.append(f"   Link: {art.url}")
            if art.summary:
                summary_snippet = art.summary[:200].replace("\n", " ").strip()
                if len(art.summary) > 200:
                    summary_snippet += "..."
                lines.append(f"   Summary: {summary_snippet}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_html(articles: list[Article]) -> str:
        """Format articles as a responsive styled HTML email."""
        items_html: list[str] = []

        for art in articles:
            category_badge = (
                f'<span style="display:inline-block;padding:2px 8px;font-size:11px;font-weight:600;'
                f'background:#2563eb;color:#ffffff;border-radius:12px;margin-right:6px;">{art.category}</span>'
                if art.category
                else ""
            )
            source_badge = (
                f'<span style="display:inline-block;padding:2px 8px;font-size:11px;'
                f'background:#374151;color:#d1d5db;border-radius:12px;">{art.source}</span>'
                if art.source
                else ""
            )
            summary_p = (
                f'<p style="margin:8px 0 0;font-size:14px;color:#9ca3af;line-height:1.5;">{art.summary[:300]}...</p>'
                if art.summary
                else ""
            )

            items_html.append(
                f"""
                <div style="background:#1f2937;border:1px solid #374151;border-radius:8px;padding:16px;margin-bottom:14px;">
                    <div style="margin-bottom:8px;">
                        {category_badge}
                        {source_badge}
                    </div>
                    <a href="{art.url}" style="font-size:16px;font-weight:bold;color:#60a5fa;text-decoration:none;" target="_blank">
                        {art.title}
                    </a>
                    {summary_p}
                </div>
                """
            )

        content_body = "".join(items_html) if items_html else '<p style="color:#9ca3af;">No highlights found for this period.</p>'
        now_str = datetime.now(tz=timezone.utc).strftime("%A, %b %d, %Y")

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI & Agents Highlights</title>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#111827;color:#f3f4f6;margin:0;padding:24px;">
    <div style="max-width:640px;margin:0 auto;background:#111827;border-radius:12px;">
        <div style="border-bottom:2px solid #374151;padding-bottom:16px;margin-bottom:20px;">
            <h1 style="margin:0 0 6px;font-size:22px;color:#f9fafb;">AI & Agents Pulse</h1>
            <p style="margin:0;font-size:13px;color:#9ca3af;">Curated highlights for {now_str} • {len(articles)} stories</p>
        </div>

        {content_body}

        <div style="border-top:1px solid #374151;margin-top:24px;padding-top:16px;font-size:12px;color:#6b7280;text-align:center;">
            Sent automatically by AI Intelligence Dashboard
        </div>
    </div>
</body>
</html>"""


class GmailSender:
    """Dispatches emails through Gmail's SMTP service using an App Password."""

    def __init__(
        self,
        user: str | None = None,
        app_password: str | None = None,
        default_recipient: str | None = None,
    ) -> None:
        load_dotenv()
        self.user = user or os.environ.get("GMAIL_USER", "").strip()
        self.app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "").strip()
        self.default_recipient = (
            default_recipient
            or os.environ.get("GMAIL_TO", "").strip()
            or self.user
        )

    def send(
        self,
        subject: str,
        text_content: str,
        html_content: str,
        recipient: str | None = None,
        dry_run: bool = False,
    ) -> bool:
        """Send multipart email to recipient.

        Returns True on success, False or raises on failure.
        """
        to_email = (recipient or self.default_recipient).strip()

        if dry_run:
            logger.info("Dry-run: skipping SMTP dispatch (recipient=%r, subject=%r)", to_email or "not-set", subject)
            return True

        if not to_email:
            raise ValueError("No recipient specified (set GMAIL_TO or pass recipient).")

        if not self.user or not self.app_password:
            raise ValueError(
                "GMAIL_USER or GMAIL_APP_PASSWORD environment variables are missing."
            )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = to_email

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(self.user, self.app_password)
            server.sendmail(self.user, [to_email], msg.as_string())

        logger.info("Digest successfully sent to %s", to_email)
        return True
