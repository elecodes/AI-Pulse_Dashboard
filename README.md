# AI Intelligence Dashboard

Aggregate, classify, and explore AI-developments from TechCrunch, MIT Tech Review, The Verge, arXiv, and Hugging Face — all in one place.

## Quick start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.api.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173` for the dashboard. Run the pipeline to fetch articles:

```bash
python -m backend.scraper run
```

No API keys required. Categories are assigned automatically via keyword rules (or optionally via OpenAI/Anthropic).

## Architecture

```
Scraper(s)  →  Normalizer  →  Classifier  →  Storage  →  API  →  Frontend
 ─────           ─────          ─────         ─────       ───      ───────
 5 feeds       Canonical      Rule or       SQLite      FastAPI   React 19
               Article        LLM                      + FTS5    + Recharts
               dataclass
```

- **Five scrapers:** RSS (3), arXiv API (4 categories), Hugging Face API
- **Normalizer:** Converts raw feed entries to a canonical `Article` dataclass
- **Classifier:** Keyword-based out of the box; optional OpenAI/Anthropic for LLM-powered
- **Storage:** SQLite with upsert by URL, FTS5 full-text search, run tracking
- **API:** FastAPI with pagination, filtering, FTS5 search, auto OpenAPI docs at `/docs`
- **Frontend:** React 19 + Vite + Recharts, dark theme, responsive (375px–1920px)

## Configuration

### feeds.yaml

```yaml
feeds:
  - name: techcrunch-ai
    type: rss
    url: https://techcrunch.com/category/artificial-intelligence/feed/

  - name: arxiv-cs-ai
    type: arxiv
    url: https://export.arxiv.org/api/query
    categories: [cs.AI, cs.LG, cs.CL, cs.CV]
```

Any field overridable via `AIID_<FIELD>` env var:
```bash
export AIID_LOOKBACK_HOURS=24
export AIID_LLM_PROVIDER=openai   # enables LLM classification
export OPENAI_API_KEY=sk-...
```

## API

| Endpoint | Params | Description |
|---|---|---|
| `GET /articles` | `page`, `page_size`, `category`, `source`, `date_from`, `date_to`, `q` | Paginated + filtered article list with FTS5 search |
| `GET /articles/{id}` | — | Single article |
| `GET /trends` | `days` (default 7) | Volume per category per day |
| `GET /sources` | — | Sources with last scrape timestamp |

## Testing

```bash
# Backend — 254 tests
python -m pytest

# Frontend — 12 component tests
cd frontend && npm test
```

- Unit tests for scrapers, normalizer, storage, pipeline, classifier, config
- Property-based tests with Hypothesis (round-trips, resilience, dedup, dry-run)
- Integration tests for API (200/400/404, pagination, filters)
- Component tests for ArticleTable and TrendChart

## Project structure

```
backend/
├── scraper/          rss.py, arxiv.py, huggingface.py
├── normalizer/       normalizer.py
├── classifier/       base.py, rule.py, classifier.py, openai.py, anthropic.py
├── storage/          storage_layer.py
├── pipeline/         pipeline.py, scheduler.py
├── api/              main.py, routers/articles.py, trends.py, sources.py
├── config/           config_loader.py, feeds.yaml
└── models/           article.py
frontend/
├── src/
│   ├── components/   ArticleTable, TrendChart, Filters, Pagination, etc.
│   ├── hooks/        useArticles, useTrends, useSources
│   └── pages/        Dashboard
docs/
└── adr/              Architecture Decision Records
```

## Architecture decisions

See [docs/adr/](docs/adr/) for the full record of why each component was built the way it was.
