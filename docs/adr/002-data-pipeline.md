# ADR 002: Data Pipeline — Scraper → Normalizer → Classifier → Storage

**Status:** Accepted

**Context:** The pipeline must ingest articles from heterogeneous sources (RSS, REST APIs), normalize them into a canonical schema, optionally classify them via LLM, and persist the result. Each stage should be independently testable and replaceable.

**Decision:**

```
Scraper(s) → [list[dict]] → Normalizer → [list[Article]] → (Classifier →) Storage
```

### Stage isolation

Each stage communicates only with the next via plain data structures:

1. **Scraper** — Returns `list[dict]` (raw feed entries). No knowledge of Article or storage.
2. **Normalizer** — Accepts `list[dict]` + source name, returns `list[Article]`. Single responsibility: convert to canonical form.
3. **Classifier** — Accepts `Article`, returns `(category, summary)`. Optional: if not configured, pipeline skips it.
4. **Storage** — Accepts `list[Article]`, persists to SQLite. Zero business logic.

### Pipeline orchestration

- `Pipeline.run()` calls each scraper, normalizes results, saves batch, then optionally classifies.
- `DryRunSaver` implements the same interface as Storage to enable dry-run mode without touching the database.
- Classification is **non-blocking**: if the classifier fails (after 3 retries), `classification_failed=True` is set and the pipeline continues.

### Error handling philosophy

| Layer | Error handling |
|---|---|
| Scraper | Non-fatal: log WARNING, return `[]`, pipeline continues |
| Normalizer | Per-article: discard malformed records, log WARNING, continue |
| Storage | Fatal: roll back transaction on write failure, raise to Pipeline |
| Classifier | Isolated: retry ×3, set `classification_failed=True` on exhaustion, never block pipeline |

**Consequences:**

- Positive: Adding a new source means writing one Scraper subclass and adding a config entry.
- Positive: Testing each stage in isolation is trivial — they're pure functions over simple types.
- Positive: The pipeline can run in a FastAPI lifespan for continuous scheduling.
- Negative: The sequential pipeline is slower than a message-queue fan-out — acceptable for <100 articles/run.
