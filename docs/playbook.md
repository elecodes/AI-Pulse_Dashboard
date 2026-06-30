# AI Intelligence Dashboard — Playbook

## Quick start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m uvicorn backend.api.main:app

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` for the dashboard and `http://localhost:8000/docs` for the API.

---

## Project structure

```
backend/
├── scraper/           # Feed fetchers (RSS, arXiv, Hugging Face)
│   ├── base.py        # AbstractScraper ABC
│   ├── rss.py         # Generic RSS
│   ├── arxiv.py       # arXiv API
│   └── huggingface.py # Hugging Face API
├── normalizer/        # Canonical Article transformation
├── classifier/        # Classification (rule-based & LLM)
│   ├── base.py        # AbstractClassifier ABC
│   ├── classifier.py  # LlmClassifier (retry, batching)
│   ├── rule.py        # RuleClassifier — keywords, no API key needed
│   ├── openai.py      # OpenAI provider
│   └── anthropic.py   # Anthropic provider
├── storage/           # SQLite persistence
├── pipeline/          # Orchestration + CLI
├── api/               # FastAPI REST endpoints
│   └── routers/       # articles, trends, sources
├── config/            # YAML config + env loader
│   └── feeds.yaml     # Feed definitions
└── models/            # Article dataclass
```

---

## Configuration

### Classification

Out of the box, the **RuleClassifier** assigns categories by scanning article titles and summaries for ~100+ keyword patterns (LLM, Computer Vision, AI Safety, Agents, etc.). No API key needed.

To use LLM-powered classification instead:

```bash
export AIID_LLM_PROVIDER=openai   # or anthropic
export OPENAI_API_KEY=sk-...
```

The RuleClassifier is automatically replaced when you set a provider. See `backend/classifier/rule.py` to extend keyword rules.

### feeds.yaml (updated 2026-06-30)

```yaml
feeds:
  - name: techcrunch-ai
    type: rss
    url: https://techcrunch.com/category/artificial-intelligence/feed/
    enabled: true

  - name: mit-tech-review-ai
    type: rss
    url: https://www.technologyreview.com/feed/
    enabled: true

  - name: verge-ai
    type: rss
    url: https://www.theverge.com/rss/index.xml
    enabled: true

  - name: arxiv-cs-ai
    type: arxiv
    url: https://export.arxiv.org/api/query
    categories: [cs.AI, cs.LG, cs.CL, cs.CV]
    enabled: true

  - name: huggingface-trending
    type: huggingface
    url: https://huggingface.co/api/models
    enabled: true

lookback_hours: 48
run_interval_minutes: 60
pipeline_timeout_seconds: 300
db_path: data/articles.db
json_export_path: data/articles.json
```

### Environment overrides

Any `AppConfig` field can be overridden with `AIID_<FIELD>`:

```bash
export AIID_DB_PATH=/tmp/test.db
export AIID_LOOKBACK_HOURS=24
export AIID_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

---

## Running the pipeline

```bash
# One-shot scrape
python -m backend.scraper run

# Dry run (don't touch DB)
python -m backend.scraper run --dry-run

# Schedule (runs every N minutes per config)
python -m backend.scraper schedule
```

---

## API endpoints

| Method | Path | Params | Description |
|---|---|---|---|
| GET | `/articles` | `page`, `page_size`, `category`, `source`, `date_from`, `date_to`, `q` | Paginated articles |
| GET | `/articles/{id}` | — | Single article |
| GET | `/trends` | `days` (default 7) | Volume per category per day |
| GET | `/sources` | — | Sources with last scrape |

All errors return JSON with `{"detail": ...}`.

---

## Testing

```bash
# Backend — all tests
python -m pytest

# Backend — with coverage
python -m pytest --cov=backend --cov-report=term-missing

# Backend — specific suite
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/property/

# Frontend
cd frontend && npm test
```

### What's tested

- **Unit tests (192):** Scrapers, normalizer, storage, pipeline, classifier, config loader
- **Property-based tests (28):** Invariants verified with Hypothesis (round-trips, resilience, dedup, dry-run, logging)
- **Integration tests (19):** API endpoints at 200/400/404, pagination, filters
- **Component tests (12):** ArticleTable and TrendChart loading/error/data states

---

## Adding a new scraper

1. Create `backend/scraper/mysource.py` extending `AbstractScraper`
2. Implement `fetch() -> list[dict]`
3. Register in `config/feeds.yaml`:

```yaml
- name: my-source
  type: mysource
  url: https://...
  enabled: true
```

No other code changes needed. The `_build_scraper` factory in `pipeline.py` dispatches by type name.

---

## Adding an LLM provider

1. Create `backend/classifier/mycoolai.py` extending `LlmClassifier`
2. Implement `_classify_single(article) -> tuple[str, str]` calling the provider's REST API via httpx
3. Register in `backend/api/routers/articles.py` or set `AIID_LLM_PROVIDER=mycoolai`

---

## Architecture decisions

See `docs/adr/` for the full record:

| ADR | Topic |
|---|---|
| 001 | Project structure & technology stack |
| 002 | Data pipeline architecture |
| 003 | LLM Classification strategy |
| 004 | REST API design |
| 005 | Frontend architecture |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| SSEGFAULT on M1/M2 | feedparser with system Python | Use `.venv` Python 3.11+ |
| `/docs` returns 404 | Backend not running | `uvicorn backend.api.main:app --reload` |
| "FTS5 not available" | SQLite compiled without FTS5 | Use Python from Homebrew: `brew install python@3.11` |
| No LLM-powered categories | Missing API key | `export OPENAI_API_KEY=...` (RuleClassifier works without it) |
| Empty article feed | Pipeline hasn't run yet | `python -m backend.scraper run` |

---

## Production considerations

- Swap SQLite for PostgreSQL when dataset exceeds 100K articles
- Add rate limiting to API (slowapi middleware)
- Containerize with Docker for reproducible deploys
- Replace Vite proxy with nginx for production frontend serving
- Add auth (API key or OAuth) before exposing publicly
