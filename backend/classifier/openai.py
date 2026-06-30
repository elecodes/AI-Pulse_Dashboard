"""OpenAIClassifier — classifies articles via the OpenAI Chat Completions API.

Uses ``httpx`` (not the OpenAI SDK) to avoid extra dependencies.
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


class OpenAIClassifier(LlmClassifier):
    """Classifier that calls the OpenAI Chat Completions API.

    Parameters
    ----------
    batch_size:
        Number of articles per batch (default 20).
    api_key:
        OpenAI API key.  Defaults to the ``OPENAI_API_KEY`` environment
        variable.
    model:
        OpenAI model identifier (default ``"gpt-4o-mini"``).
    """

    def __init__(
        self,
        batch_size: int = 20,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        super().__init__(batch_size)
        self._api_key = api_key or os.environ["OPENAI_API_KEY"]
        self._model = model
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _classify_single(self, article: Article) -> tuple[str, str]:
        """Send the article to OpenAI and return ``(category, summary)``."""
        prompt = _PROMPT_TEMPLATE.format(
            title=article.title,
            content=article.summary or "No content available.",
        )
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        category, summary = self._parse_response(content)
        return category, self._truncate_summary(summary)
