"""Canonical Article schema for the AI Intelligence Dashboard.

This dataclass is the single source of truth for article data throughout the
entire pipeline. It is defined once in Sprint 1 and never broken — Sprint 2+
only adds optional fields with defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _default_serializer(obj: Any) -> Any:
    """Fallback serializer for types that json.dumps cannot handle natively.

    Tries __dict__ first (plain objects), then falls back to repr so that
    serialization never raises — the raw payload must always be preserved.
    """
    try:
        return obj.__dict__
    except AttributeError:
        return repr(obj)


@dataclass
class Article:
    """Canonical representation of a single scraped article.

    Fields
    ------
    id : str
        UUID v4 string, generated at normalization time.
    title : str
        Article headline.
    url : str
        Canonical URL — unique key in the storage layer.
    source : str
        Logical scraper name (e.g. "techcrunch-ai", "arxiv-cs-ai").
    published_at : str | None
        UTC ISO 8601 timestamp ("YYYY-MM-DDTHH:MM:SSZ").  ``None`` when the
        original timestamp could not be parsed.
    fetched_at : str
        UTC ISO 8601 timestamp set at normalization time.
    summary : str | None
        Article abstract or excerpt, max 2 000 characters.  ``None`` when not
        available.
    authors : list[str]
        Author names; empty list when the source does not provide them.
    tags : list[str]
        Taxonomy tags; empty in Sprint 1, populated by Sprint 2+ classifiers.
    category : str | None
        LLM-assigned category; ``None`` until Sprint 2 classification.
    raw : dict[str, Any]
        Original source payload, preserved verbatim.
    """

    id: str
    title: str
    url: str
    source: str
    published_at: str | None
    fetched_at: str
    summary: str | None
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    classification_failed: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize the Article to a deterministic JSON string.

        Keys are sorted alphabetically (``sort_keys=True``) to guarantee
        that two Articles with the same data always produce identical JSON —
        a requirement for the round-trip property test (Property 8).

        Non-serializable values inside ``raw`` are handled by
        ``_default_serializer`` so the method never raises.
        """
        return json.dumps(
            {
                "id": self.id,
                "title": self.title,
                "url": self.url,
                "source": self.source,
                "published_at": self.published_at,
                "fetched_at": self.fetched_at,
                "summary": self.summary,
                "authors": self.authors,
                "tags": self.tags,
                "category": self.category,
                "classification_failed": self.classification_failed,
                "raw": self.raw,
            },
            sort_keys=True,
            default=_default_serializer,
        )

    @classmethod
    def from_json(cls, s: str) -> Article:
        """Deserialize an Article from a JSON string produced by ``to_json``.

        Parameters
        ----------
        s:
            JSON string as returned by ``Article.to_json()``.

        Returns
        -------
        Article
            Reconstructed Article instance.

        Raises
        ------
        KeyError
            If a required field is missing from the JSON payload.
        json.JSONDecodeError
            If ``s`` is not valid JSON.
        """
        data: dict[str, Any] = json.loads(s)
        return cls(
            id=data["id"],
            title=data["title"],
            url=data["url"],
            source=data["source"],
            published_at=data["published_at"],
            fetched_at=data["fetched_at"],
            summary=data["summary"],
            authors=data.get("authors", []),
            tags=data.get("tags", []),
            category=data.get("category"),
            classification_failed=data.get("classification_failed", False),
            raw=data.get("raw", {}),
        )
