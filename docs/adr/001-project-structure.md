# ADR 001: Project Structure and Technology Stack

**Status:** Accepted

**Context:** The AI Intelligence Dashboard needs a modular, testable architecture that can ingest data from multiple sources, enrich it, and serve a frontend. The project must be easy to reason about, easy to extend, and require minimal operational overhead.

**Decision:**

### Monorepo layout

```
ai-intel-dashboard/
├── backend/
│   ├── scraper/        # Feed fetchers (RSS, arXiv, Hugging Face)
│   ├── normalizer/     # Canonical Article transformation
│   ├── classifier/     # LLM-based classification
│   ├── storage/        # SQLite persistence
│   ├── pipeline/       # Orchestration
│   ├── api/            # FastAPI REST endpoints
│   └── config/         # YAML + env config loader
├── frontend/
│   └── src/
│       ├── components/  # React components
│       ├── hooks/       # Data-fetching hooks
│       └── pages/       # Route pages
├── tests/
│   ├── unit/
│   ├── integration/
│   └── property/
└── docs/
    └── adr/
```

### Technology choices

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Existing ecosystem for feeds (feedparser), SQL (SQLAlchemy), HTTP (httpx) |
| Storage | SQLite | Zero ops, single file, FTS5 built-in, sufficient for single-user dashboard |
| Pipeline | Synchronous thread-per-scraper | Simpler than async for IO-bound feed fetches; FastAPI lifespan can wrap it later |
| API | FastAPI | Native async, auto OpenAPI docs, Pydantic integration, CORS built-in |
| Classifier | httpx + tenacity | No extra SDK deps; retry with exponential backoff is a language concern, not a library concern |
| Frontend | React 19 + Vite + TypeScript | Fast dev iteration, native ESM, strong typing |
| Charts | Recharts | Composable, React-native, stacked bar charts out of the box |

**Consequences:**

- Positive: New scraper sources only require a single file + config entry; no other code changes.
- Positive: The entire backend can be run from a single Python process; no Docker or message queues needed.
- Positive: Frontend proxies to backend via Vite in dev; no CORS issues.
- Negative: SQLite doesn't support concurrent writes at scale — acceptable for a personal dashboard.
- Negative: Pipeline scrapes sequentially per source; parallelization would need asyncio refactor.
