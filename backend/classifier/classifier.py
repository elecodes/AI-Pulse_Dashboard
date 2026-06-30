"""LlmClassifier — abstract base for LLM-based article classifiers.

Provides batching, tenacity-based retry with exponential backoff, and
error handling that sets ``classification_failed`` on articles whose
classification permanently fails.
"""

from __future__ import annotations

import logging
from abc import abstractmethod

from tenacity import retry, stop_after_attempt, wait_exponential

from backend.classifier.base import AbstractClassifier, ClassificationError
from backend.models.article import Article

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class LlmClassifier(AbstractClassifier):
    """Abstract classifier that adds batching and tenacity retry logic.

    Subclasses must implement :meth:`_classify_single`, which performs
    the actual LLM API call and returns ``(category, summary)``.

    Parameters
    ----------
    batch_size:
        Number of articles processed per batch (default 20).
    """

    def __init__(self, batch_size: int = 20) -> None:
        self._batch_size = batch_size

    # ------------------------------------------------------------------
    # Subclass API
    # ------------------------------------------------------------------

    @abstractmethod
    def _classify_single(self, article: Article) -> tuple[str, str]:
        """Call the LLM API for a single article.

        Returns
        -------
        tuple[str, str]
            ``(category, summary)``.

        Raises
        ------
        Exception
            Any exception triggers a retry via tenacity.
        """

    # ------------------------------------------------------------------
    # Retry-aware classify
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _classify_with_retry(self, article: Article) -> tuple[str, str]:
        """Tenacity-wrapped call to ``_classify_single``."""
        return self._classify_single(article)

    def classify(self, article: Article) -> tuple[str, str]:
        """Classify a single article with up to 3 retries.

        Raises
        ------
        ClassificationError
            After all retries are exhausted.
        """
        try:
            return self._classify_with_retry(article)
        except Exception as exc:
            raise ClassificationError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def classify_batch(self, articles: list[Article]) -> list[Article]:
        """Classify a batch of articles with retry and error isolation.

        Articles are processed in groups of ``batch_size``.  A failure on
        any individual article (after retries) sets
        ``article.classification_failed = True`` but does NOT affect other
        articles in the batch.

        Parameters
        ----------
        articles:
            Articles to classify.  Modified in place.

        Returns
        -------
        list[Article]
            Same list as *articles*, with ``category``, ``summary``, and
            ``classification_failed`` updated.
        """
        for i in range(0, len(articles), self._batch_size):
            batch = articles[i : i + self._batch_size]
            for article in batch:
                try:
                    category, summary = self.classify(article)
                    article.category = category
                    article.summary = summary
                except ClassificationError:
                    article.classification_failed = True

        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(content: str) -> tuple[str, str]:
        """Parse ``CATEGORY:`` / ``SUMMARY:`` format from an LLM response.

        Returns
        -------
        tuple[str, str]
            ``(category, summary)``.  Either value may be an empty string
            if the corresponding label was not found.
        """
        category = ""
        summary = ""
        for line in content.strip().split("\n"):
            line = line.strip()
            if line.upper().startswith("CATEGORY:"):
                category = line[len("CATEGORY:"):].strip()
            elif line.upper().startswith("SUMMARY:"):
                summary = line[len("SUMMARY:"):].strip()
        return category, summary

    @staticmethod
    def _truncate_summary(text: str, max_words: int = 150) -> str:
        """Truncate *text* to at most *max_words* words."""
        words = text.split()
        if len(words) <= max_words:
            return text
        return " ".join(words[:max_words])
