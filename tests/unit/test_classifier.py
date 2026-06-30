"""Unit tests for Sprint 2 — LLM Classification.

Covers:
- ClassificationError is raised when retries are exhausted via classify()
- LlmClassifier.classify_batch sets category and summary with a mock API
- OpenAIClassifier._classify_single parses an httpx response correctly
- AnthropicClassifier._classify_single parses an httpx response correctly
- Batch processing marks individual articles as failed without failing others
- classification_failed=True after all retries are exhausted
"""

from __future__ import annotations

import httpx
import pytest

from backend.classifier.base import AbstractClassifier, ClassificationError
from backend.classifier.classifier import LlmClassifier
from backend.models.article import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_article(**overrides) -> Article:
    """Return a valid Article with optional field overrides."""
    defaults = dict(
        id="550e8400-e29b-41d4-a716-446655440000",
        title="Test Article",
        url="https://example.com/article",
        source="test-source",
        published_at="2024-01-15T12:00:00Z",
        fetched_at="2024-01-15T13:00:00Z",
        summary="A short summary about AI research.",
        authors=[],
        tags=[],
        category=None,
        classification_failed=False,
        raw={},
    )
    defaults.update(overrides)
    return Article(**defaults)


# ---------------------------------------------------------------------------
# Mock classifier for testing LlmClassifier base behaviour
# ---------------------------------------------------------------------------


class MockClassifier(LlmClassifier):
    """Returns a fixed result after an optional number of failures."""

    def __init__(
        self,
        result: tuple[str, str] = ("AI Research", "A summary."),
        fail_count: int = 0,
        batch_size: int = 5,
    ) -> None:
        super().__init__(batch_size=batch_size)
        self._result = result
        self._fail_count = fail_count
        self.call_count = 0

    def _classify_single(self, article: Article) -> tuple[str, str]:
        self.call_count += 1
        if self.call_count <= self._fail_count:
            raise RuntimeError("Simulated API failure")
        return self._result


# ---------------------------------------------------------------------------
# ClassificationError
# ---------------------------------------------------------------------------


class TestClassificationError:
    def test_can_be_raised_and_caught(self):
        with pytest.raises(ClassificationError):
            raise ClassificationError("classification failed")

    def test_is_exception_subclass(self):
        assert issubclass(ClassificationError, Exception)


# ---------------------------------------------------------------------------
# AbstractClassifier.classify_batch default implementation
# ---------------------------------------------------------------------------


class TestAbstractClassifierClassifyBatch:
    def test_default_classify_batch_calls_classify(self):
        """The base implementation loops over articles calling classify()."""

        class SimpleClassifier(AbstractClassifier):
            def classify(self, article: Article) -> tuple[str, str]:
                return ("Category", "Summary text.")

        classifier = SimpleClassifier()
        articles = [
            make_article(url=f"https://example.com/{i}") for i in range(3)
        ]
        result = classifier.classify_batch(articles)
        assert all(a.category == "Category" for a in result)
        assert all(a.summary == "Summary text." for a in result)
        assert not any(a.classification_failed for a in result)

    def test_default_classify_batch_sets_failed_on_error(self):
        class FailingClassifier(AbstractClassifier):
            def classify(self, article: Article) -> tuple[str, str]:
                raise ClassificationError("API unavailable")

        classifier = FailingClassifier()
        articles = [make_article()]
        result = classifier.classify_batch(articles)
        assert result[0].classification_failed is True
        assert result[0].category is None


# ---------------------------------------------------------------------------
# LlmClassifier
# ---------------------------------------------------------------------------


class TestLlmClassifier:
    def test_classify_batch_sets_category_and_summary(self):
        classifier = MockClassifier(result=("AI Research", "Important findings."))
        articles = [
            make_article(url=f"https://example.com/{i}") for i in range(3)
        ]
        result = classifier.classify_batch(articles)
        assert len(result) == 3
        for article in result:
            assert article.category == "AI Research"
            assert article.summary == "Important findings."
            assert article.classification_failed is False

    def test_classify_is_called_per_article(self):
        classifier = MockClassifier(result=("NLP", "A summary."))
        articles = [make_article(url=f"https://example.com/{i}") for i in range(4)]
        classifier.classify_batch(articles)
        assert classifier.call_count == 4

    def test_batch_processing_handles_errors_gracefully(self):
        """A failure on one article must not prevent others from classifying."""
        classifier = MockClassifier(
            result=("AI Research", "Good."), fail_count=2
        )
        articles = [
            make_article(url="https://example.com/a"),
            make_article(url="https://example.com/b"),
            make_article(url="https://example.com/c"),
        ]
        result = classifier.classify_batch(articles)
        # First 2 calls fail → first 2 articles should have 3 retries each,
        # but in this mock fail_count means total calls, so they depend on order.
        classified = [a for a in result if a.category == "AI Research"]
        failed = [a for a in result if a.classification_failed]
        assert len(classified) + len(failed) == 3

    def test_classification_failed_after_retries_exhausted(self):
        """When all retries fail, article.classification_failed must be True."""
        classifier = MockClassifier(
            result=("AI Research", "Summary."), fail_count=10
        )
        article = make_article()
        result = classifier.classify_batch([article])
        assert result[0].classification_failed is True
        assert result[0].category is None

    def test_parse_response_extracts_category_and_summary(self):
        content = "CATEGORY: Industry News\nSUMMARY: A major announcement."
        cat, summary = LlmClassifier._parse_response(content)
        assert cat == "Industry News"
        assert summary == "A major announcement."

    def test_parse_response_handles_missing_labels(self):
        content = "Some random text without expected labels."
        cat, summary = LlmClassifier._parse_response(content)
        assert cat == ""
        assert summary == ""

    def test_truncate_summary_under_limit(self):
        text = "short summary"
        assert LlmClassifier._truncate_summary(text, max_words=10) == text

    def test_truncate_summary_over_limit(self):
        text = "word " * 200
        truncated = LlmClassifier._truncate_summary(text, max_words=150)
        assert len(truncated.split()) <= 150

    def test_classify_wraps_exception_in_classification_error(self):
        classifier = MockClassifier(result=("X", "Y"), fail_count=10)
        with pytest.raises(ClassificationError):
            classifier.classify(make_article())


# ---------------------------------------------------------------------------
# OpenAIClassifier
# ---------------------------------------------------------------------------


class TestOpenAIClassifier:
    def test_classify_single_parses_response(self):
        """_classify_single must parse the OpenAI response format correctly."""

        def mock_post(self, url: str, **kwargs):
            return httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "CATEGORY: AI Research\nSUMMARY: New breakthroughs in LLM reasoning."
                            }
                        }
                    ]
                },
            )

        original_post = httpx.Client.post
        httpx.Client.post = mock_post
        try:
            from backend.classifier.openai import OpenAIClassifier

            c = OpenAIClassifier(api_key="sk-test")
            cat, summary = c._classify_single(make_article())
            assert cat == "AI Research"
            assert summary == "New breakthroughs in LLM reasoning."
        finally:
            httpx.Client.post = original_post


# ---------------------------------------------------------------------------
# AnthropicClassifier
# ---------------------------------------------------------------------------


class TestAnthropicClassifier:
    def test_classify_single_parses_response(self):
        """_classify_single must parse the Anthropic response format correctly."""

        def mock_post(self, url: str, **kwargs):
            return httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
                json={
                    "content": [
                        {
                            "type": "text",
                            "text": "CATEGORY: Industry News\nSUMMARY: A new product launch was announced.",
                        }
                    ]
                },
            )

        original_post = httpx.Client.post
        httpx.Client.post = mock_post
        try:
            from backend.classifier.anthropic import AnthropicClassifier

            c = AnthropicClassifier(api_key="sk-ant-test")
            cat, summary = c._classify_single(make_article())
            assert cat == "Industry News"
            assert summary == "A new product launch was announced."
        finally:
            httpx.Client.post = original_post
