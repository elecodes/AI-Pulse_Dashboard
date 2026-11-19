"""Unit tests for the newsletter digest module."""

from unittest.mock import MagicMock, patch

import pytest

from backend.digest.newsletter import DigestCollector, DigestFormatter, GmailSender
from backend.models.article import Article


@pytest.fixture
def sample_articles():
    return [
        Article(
            id="art-1",
            title="OpenAI announces Autonomous Agent Swarm",
            url="https://example.com/agent-swarm",
            source="techcrunch-ai",
            published_at="2026-11-19T10:00:00Z",
            fetched_at="2026-11-19T10:05:00Z",
            summary="A comprehensive overview of new multi-agent systems.",
            authors=["Tech Author"],
            tags=["AI", "Agents"],
            category="Agents",
        ),
        Article(
            id="art-2",
            title="New LLM Reasoning Benchmark",
            url="https://example.com/reasoning-benchmark",
            source="arxiv-cs-ai",
            published_at="2026-11-18T14:30:00Z",
            fetched_at="2026-11-18T15:00:00Z",
            summary="Evaluating reasoning capabilities in frontier models.",
            authors=["Researcher"],
            tags=["LLM"],
            category="LLM",
        ),
    ]


def test_format_text(sample_articles):
    text = DigestFormatter.format_text(sample_articles)
    assert "AI & AGENTS - HIGHLIGHTS DIGEST" in text
    assert "OpenAI announces Autonomous Agent Swarm" in text
    assert "https://example.com/agent-swarm" in text
    assert "[Agents]" in text


def test_format_html(sample_articles):
    html = DigestFormatter.format_html(sample_articles)
    assert "<!DOCTYPE html>" in html
    assert "OpenAI announces Autonomous Agent Swarm" in html
    assert "https://example.com/agent-swarm" in html
    assert "Agents" in html


def test_collector_fetches_articles(sample_articles):
    storage_mock = MagicMock()
    storage_mock.get_articles.return_value = sample_articles

    collector = DigestCollector(storage_mock)
    articles = collector.collect(days=3, limit=10)

    assert len(articles) == 2
    assert storage_mock.get_articles.called


def test_gmail_sender_dry_run():
    sender = GmailSender(user="test@gmail.com", app_password="password", default_recipient="target@gmail.com")
    result = sender.send(
        subject="Test",
        text_content="Plain text",
        html_content="<p>HTML</p>",
        dry_run=True,
    )
    assert result is True


def test_gmail_sender_missing_credentials():
    sender = GmailSender(user="", app_password="")
    with pytest.raises(ValueError, match="missing"):
        sender.send(
            subject="Test",
            text_content="Plain text",
            html_content="<p>HTML</p>",
            recipient="test@gmail.com",
            dry_run=False,
        )


@patch("smtplib.SMTP")
def test_gmail_sender_smtp_mock(mock_smtp):
    instance = MagicMock()
    mock_smtp.return_value.__enter__.return_value = instance

    sender = GmailSender(
        user="test@gmail.com",
        app_password="secret-password",
        default_recipient="dest@gmail.com",
    )
    result = sender.send(
        subject="Weekly Highlights",
        text_content="Hello world",
        html_content="<p>Hello world</p>",
        recipient="dest@gmail.com",
        dry_run=False,
    )

    assert result is True
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("test@gmail.com", "secret-password")
    assert instance.sendmail.called
