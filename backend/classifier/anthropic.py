"""AnthropicClassifier — classifies articles via the Anthropic Messages API.

Uses ``httpx`` (not the Anthropic SDK) to avoid extra dependencies.
"""

from __future__ import annotations

import os

import httpx

from backend.classifier.classifier import LlmClassifier
from backend.models.article import Article

_PROMPT_TEMPLATE = """Classify the following article into a category and provide a brief summary (max 150 words).

Title: {title}
Content: {content}

Respond with exactly:
CATEGORY: <category>
SUMMARY: <summary>"""


class AnthropicClassifier(LlmClassifier):
    """Classifier that calls the Anthropic Messages API.

    Parameters
    ----------
    batch_size:
        Number of articles per batch (default 20).
    api_key:
        Anthropic API key.  Defaults to the ``ANTHROPIC_API_KEY`` environment
        variable.
    model:
        Anthropic model identifier (default ``"claude-3-5-haiku-20241022"``).
    """

    def __init__(
        self,
        batch_size: int = 20,
        api_key: str | None = None,
        model: str = "claude-3-5-haiku-20241022",
    ) -> None:
        super().__init__(batch_size)
        self._api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self._model = model
        self._client = httpx.Client(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _classify_single(self, article: Article) -> tuple[str, str]:
        """Send the article to Anthropic and return ``(category, summary)``."""
        prompt = _PROMPT_TEMPLATE.format(
            title=article.title,
            content=article.summary or "No content available.",
        )
        response = self._client.post(
            "/v1/messages",
            json={
                "model": self._model,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        data = response.json()
        text = data["content"][0]["text"]
        category, summary = self._parse_response(text)
        return category, self._truncate_summary(summary)
