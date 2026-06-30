"""Abstract classifier interface — Sprint 2 extensibility seam.

Sprint 1 ships the stub only. Sprint 2 drops in ``OpenAIClassifier`` and
``AnthropicClassifier`` without touching any Sprint 1 code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.article import Article


class ClassificationError(Exception):
    """Raised when article classification fails after exhausting all retries."""


class AbstractClassifier(ABC):
    @abstractmethod
    def classify(self, article: Article) -> tuple[str, str]:
        """Returns (category, summary). Raises ClassificationError after retries."""
        ...

    def classify_batch(self, articles: list[Article]) -> list[Article]:
        """Classify a batch of articles. Returns updated articles.

        Default implementation iterates over articles and calls ``classify``
        on each one.  Subclasses MAY override to add batching, parallelism,
        or retry logic.
        """
        for article in articles:
            try:
                category, summary = self.classify(article)
                article.category = category
                article.summary = summary
            except ClassificationError:
                article.classification_failed = True
        return articles
