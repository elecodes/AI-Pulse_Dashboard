# Implementation Plan: AI Intelligence Dashboard — Sprint 1

## Overview

Implement the Python backend data pipeline: project scaffolding, canonical Article schema, config
loader, logging, all three scrapers, normalizer, storage layer, pipeline orchestrator, scheduler,
and CLI entry point. Sprint 2–5 items are stubbed where they form explicit extensibility seams.
All 15 correctness properties are covered by property-based tests using `hypothesis`.

---

## Tasks

- [x] 1. Project scaffolding
  - Create directory tree matching design: `backend/`, `config/`, `data/`, `tests/unit/`,
    `tests/property/`, `tests/integration/`
  - Write `pyproject.toml` with pinned runtime deps (`feedparser`, `httpx`, `tenacity`,
    `python-dateutil`, `pydantic-settings`, `apscheduler`, `sqlalchemy`, `pyyaml`) and dev deps
    (`pytest`, `pytest-cov`, `hypothesis`)
  - Write `.env.example` documenting all `AIID_*`, `LOG_FORMAT`, `LOG_LEVEL`, `LOG_FILE` variables
  - Write `README.md` setup section: venv creation, `pip install -e .[dev]`, run commands
  - Add Python version guard in a `check_python_version()` helper (prints error + exits non-zero
    if `sys.version_info < (3, 11)`)
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Canonical Article schema (`backend/models/article.py`)
  - [x] 2.1 Implement `Article` dataclass with all Sprint 1 fields
    - Fields: `id`, `title`, `url`, `source`, `published_at`, `fetched_at`, `summary`, `authors`,
      `tags`, `category`, `raw` — matching the design schema exactly
    - Add `to_json() -> str` (deterministic key order via `sort_keys=True`) and
      `from_json(s: str) -> Article` class method
    - _Requirements: 5.1, 5.6, 5.7_

  - [ ]\* 2.2 Write property test for Article round-trip (Property 8)
    - `# Feature: ai-intel-dashboard, Property 8: Article serialization round-trip`
    - Use `st.builds(Article, ...)` with constrained strategies; assert
      `serialize(deserialize(serialize(A))) == serialize(A)`
    - **Property 8: Article serialization round-trip**
    - **Validates: Requirements 5.6, 5.7**

- [x] 3. Config loader (`backend/config/config_loader.py`)
  - [x] 3.1 Implement `FeedConfig` and `AppConfig` pydantic models as per design schema
    - Include all fields: `feeds`, `lookback_hours`, `run_interval_minutes`,
      `pipeline_timeout_seconds`, `db_path`, `json_export_path`
    - _Requirements: 8.1, 8.4_

  - [x] 3.2 Implement `ConfigLoader.load(path: str) -> AppConfig`
    - Parse `feeds.yaml` via `pyyaml`, merge `AIID_*` env overrides via `pydantic-settings`,
      raise `ConfigurationError` (custom exception) on any missing required field
    - Exit non-zero when called from CLI context (log ERROR + re-raise)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]\* 3.3 Write property test for config env override (Property 14)
    - `# Feature: ai-intel-dashboard, Property 14: AIID_* env vars override YAML values`
    - For any setting S, monkeypatch `AIID_<S>=V_env` and assert `config.<s> == V_env`
    - **Property 14: AIID\_\* environment variables override YAML config values**
    - **Validates: Requirements 8.3**

  - [ ]\* 3.4 Write property test for invalid config raises ConfigurationError before scraping (Property 13)
    - `# Feature: ai-intel-dashboard, Property 13: Invalid config raises ConfigurationError`
    - Generate configs with missing required fields; assert `ConfigurationError` raised and no
      scraper `fetch()` called
    - **Property 13: Invalid or incomplete config raises ConfigurationError before any scraping**
    - **Validates: Requirements 8.2, 8.5**

- [x] 4. Logging setup (`backend/logging_config.py`)
  - [x] 4.1 Implement `JsonFormatter` and `setup_logging()` function
    - `JsonFormatter.format()` emits `{"ts", "level", "logger", "message"}` minimum keys
    - `setup_logging()` reads `LOG_FORMAT`, `LOG_LEVEL`, `LOG_FILE` env vars; attaches stdout
      handler always; adds `FileHandler` when `LOG_FILE` is set
    - _Requirements: 9.1, 9.2, 9.4_

  - [ ]\* 4.2 Write property test for JSON log format (Property 15)
    - `# Feature: ai-intel-dashboard, Property 15: JSON log format emits valid parseable JSON`
    - Emit log events at all levels with `LOG_FORMAT=json`; assert each line parses as JSON and
      contains `ts`, `level`, `logger`, `message`
    - **Property 15: JSON log format emits valid, parseable JSON per log event**
    - **Validates: Requirements 9.1**

- [x] 5. AbstractScraper ABC (`backend/scraper/base.py`)
  - Define `AbstractScraper` with abstract `fetch(self) -> list[dict[str, Any]]` and abstract
    property `source_name` as per design interface
  - `fetch()` contract: never raises; logs and returns `[]` on failure
  - _Requirements: 2.1, 2.4, 2.5_

- [x] 6. RSSNewsScraper (`backend/scraper/rss.py`)
  - [x] 6.1 Implement `RSSNewsScraper(AbstractScraper)`
    - Use `feedparser` for RSS/Atom parsing; apply look-back window filter (drop entries older than
      `lookback_hours`); deduplicate by URL before returning
    - Catch all fetch/parse exceptions, log WARNING with source name + error, return `[]`
    - Extract: `title`, `url` (`link`), `published_at` (from `entry.published`), `source`,
      `summary`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]\* 6.2 Write property test for scraper look-back window filter (Property 1)
    - `# Feature: ai-intel-dashboard, Property 1: Scraper look-back window filter`
    - Generate synthetic feed entries with timestamps spanning before/after the window; assert all
      returned records fall within the configured window
    - **Property 1: Scraper look-back window filter**
    - **Validates: Requirements 2.2, 3.3**

  - [ ]\* 6.3 Write property test for scraper resilience (Property 2)
    - `# Feature: ai-intel-dashboard, Property 2: Scraper resilience — failed source does not halt pipeline`
    - Simulate unreachable URLs and malformed content; assert `fetch()` returns `[]` without raising
    - **Property 2: Scraper resilience — failed source does not halt pipeline**
    - **Validates: Requirements 2.4, 2.5, 4.3**

  - [ ]\* 6.4 Write property test for scraper output deduplication (Property 3)
    - `# Feature: ai-intel-dashboard, Property 3: Scraper output deduplication`
    - Generate raw record lists with intentional URL duplicates; assert no two returned records
      share the same URL
    - **Property 3: Scraper output deduplication**
    - **Validates: Requirements 2.6, 3.5, 4.4**

- [x] 7. ArXivScraper (`backend/scraper/arxiv.py`)
  - [x] 7.1 Implement `ArXivScraper(AbstractScraper)`
    - Use `httpx` synchronous client to query `http://export.arxiv.org/api/query`; parse Atom
      response with `feedparser`
    - Apply look-back window filter; deduplicate by arXiv paper ID
    - Wrap HTTP call with `tenacity` retry: max 3 attempts, exponential backoff, log failure after
      final retry and return `[]`
    - Extract: paper ID, `title`, `authors` list, `summary` (abstract), `published_at`, PDF URL
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 7.2 Write unit test for ArXivScraper with a recorded Atom fixture
    - Use a local Atom XML fixture; assert correct field extraction and deduplication by paper ID
    - _Requirements: 3.2_

- [x] 8. HuggingFaceScraper (`backend/scraper/huggingface.py`)
  - [x] 8.1 Implement `HuggingFaceScraper(AbstractScraper)`
    - Use `httpx` with configurable timeout to fetch from `https://huggingface.co/api/models`
    - Fall back to fetch timestamp as `published_at` when API returns no native date
    - Deduplicate by URL; catch all errors, log WARNING, return `[]`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 8.2 Write unit test for HuggingFaceScraper fallback published_at
    - Mock API response without a native date field; assert `published_at` is set to fetch time
    - _Requirements: 4.2_

- [x] 9. Checkpoint — scrapers baseline
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Normalizer (`backend/normalizer/normalizer.py`)
  - [x] 10.1 Implement `Normalizer.normalize(raw: dict) -> Article | None`
    - Validate required fields (`title`, `url`, `published_at`); return `None` + log WARNING on
      any missing field
    - Parse timestamps via `python-dateutil`; normalize to UTC ISO 8601 `YYYY-MM-DDTHH:MM:SSZ`;
      set `published_at=None` + log WARNING if unparseable (retain record)
    - Generate `id` as `str(uuid.uuid4())`; set `fetched_at` to current UTC time
    - Implement `truncate_summary(s: str) -> str`: encode to UTF-8 bytes, slice at 2000 bytes,
      decode with `errors='ignore'`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 10.2 Implement `Normalizer.normalize_all(records: list[dict]) -> tuple[list[Article], int]`
    - Returns `(articles, discard_count)` where `discard_count` is the count of `None` results
    - _Requirements: 5.1, 5.2_

  - [ ]\* 10.3 Write property test for Normalizer complete Article from valid record (Property 4)
    - `# Feature: ai-intel-dashboard, Property 4: Normalizer produces complete Article from valid raw record`
    - Generate valid raw dicts (with all required fields); assert returned Article has all schema
      fields, valid UUID v4 `id`, UTC ISO 8601 `fetched_at`, list `authors`/`tags`, verbatim `raw`
    - **Property 4: Normalizer produces a complete Article from any valid raw record**
    - **Validates: Requirements 5.1**

  - [ ]\* 10.4 Write property test for Normalizer discards records with missing fields (Property 5)
    - `# Feature: ai-intel-dashboard, Property 5: Normalizer discards records missing required fields`
    - Generate raw dicts with at least one of `title`, `url`, `published_at` removed; assert
      `normalize()` returns `None` without raising
    - **Property 5: Normalizer discards records missing required fields**
    - **Validates: Requirements 5.2**

  - [ ]\* 10.5 Write property test for timestamp normalization to UTC ISO 8601 (Property 6)
    - `# Feature: ai-intel-dashboard, Property 6: Timestamp normalization to UTC ISO 8601`
    - Generate parseable timestamp strings in various formats/timezones; assert output matches
      `YYYY-MM-DDTHH:MM:SSZ`; generate unparseable strings; assert `published_at=None` and record
      returned (not discarded)
    - **Property 6: Timestamp normalization to UTC ISO 8601**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]\* 10.6 Write property test for summary truncation preserves UTF-8 boundary (Property 7)
    - `# Feature: ai-intel-dashboard, Property 7: Summary truncation preserves UTF-8 boundary`
    - Generate strings including multi-byte Unicode characters; assert `len(result) <= 2000` and
      result is valid UTF-8; assert strings ≤ 2000 chars are returned unchanged
    - **Property 7: Summary truncation preserves UTF-8 boundary**
    - **Validates: Requirements 5.5**

- [ ] 11. Storage layer (`backend/storage/storage_layer.py`)
  - [-] 11.1 Implement schema initialization (`Storage_Layer.init_db()`)
    - Use SQLAlchemy Core with SQLite dialect; create `articles` and `runs` tables + all indexes
      from the design SQL schema; operation must be idempotent (`CREATE TABLE IF NOT EXISTS`)
    - Create DB file and parent directories if they don't exist
    - _Requirements: 6.1, 6.7_

  - [-] 11.2 Implement `Storage_Layer.save_batch(articles: list[Article]) -> tuple[int, int]`
    - Returns `(inserted_count, deduped_count)`
    - Upsert on `url` uniqueness: on conflict, update only `fetched_at` and `raw`
    - Wrap in a single transaction; on any exception roll back and raise
    - _Requirements: 6.3, 6.8_

  - [-] 11.3 Implement `Storage_Layer.get_articles(date_from, date_to) -> list[Article]`
    - Filter by `published_at` inclusive range; order by `published_at` DESC
    - _Requirements: 6.4, 6.5_

  - [-] 11.4 Implement `Storage_Layer.export_json(path: str)`
    - Write to `<path>.tmp` then `os.replace()` for atomic swap; serialize all articles to JSON
      array
    - _Requirements: 6.2_

  - [-] 11.5 Implement run tracking (`begin_run`, `end_run`)
    - `begin_run()` inserts a row in `runs` with `status='running'`; returns `run_id`
    - `end_run(run_id, stats)` updates `ended_at`, counts, and `status`
    - _Requirements: 6.6_

  - [ ]\* 11.6 Write property test for upsert updates only fetched_at and raw (Property 9)
    - `# Feature: ai-intel-dashboard, Property 9: Upsert on duplicate URL updates only fetched_at and raw`
    - Insert Article A, then insert A′ with same URL but different fields; assert `fetched_at`/`raw`
      reflect A′ and all other fields retain A's values
    - **Property 9: Upsert on duplicate URL updates only fetched_at and raw**
    - **Validates: Requirements 6.3**

  - [ ]\* 11.7 Write property test for date-range query ordering (Property 10)
    - `# Feature: ai-intel-dashboard, Property 10: Date-range query returns articles within bounds ordered descending`
    - Insert articles with scattered `published_at` values; assert query results are within
      [start, end] and sorted descending
    - **Property 10: Date-range query returns articles within bounds, ordered descending**
    - **Validates: Requirements 6.5**

  - [ ]\* 11.8 Write property test for write failure causes full rollback (Property 11)
    - `# Feature: ai-intel-dashboard, Property 11: Write failure causes full rollback with no partial data`
    - Force a mid-batch failure (e.g., mock DB error); assert DB state before and after is
      identical and an exception is raised
    - **Property 11: Write failure causes full rollback with no partial data**
    - **Validates: Requirements 6.8**

  - [ ] 11.9 Write unit tests for storage edge cases
    - DB file auto-creation on first run; `init_db()` idempotency; run record written to `runs`
      table after pipeline completes
    - _Requirements: 6.6, 6.7_

- [ ] 12. Checkpoint — data layer
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Pipeline orchestrator (`backend/pipeline/pipeline.py`)
  - [ ] 13.1 Implement `Pipeline.run(config, dry_run=False) -> RunResult`
    - Sequence: `begin_run()` → `[scraper.fetch() for scraper in scrapers]` →
      `normalizer.normalize_all()` → `storage.save_batch()` (skipped when `dry_run=True`) →
      `storage.export_json()` (skipped when `dry_run=True`) → `end_run(stats)`
    - Log pipeline start (source list) and completion (fetched/inserted/deduped/discarded counts,
      duration in seconds)
    - Enforce timeout via `threading.Timer`; on expiry cancel run, log ERROR, record
      `status='timeout'`
    - Catch unhandled exceptions, log ERROR with full stack trace, record `status='failure'`
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6_

  - [ ]\* 13.2 Write property test for dry-run flag prevents Storage_Layer writes (Property 12)
    - `# Feature: ai-intel-dashboard, Property 12: Dry-run flag prevents all Storage_Layer writes`
    - Run pipeline with `dry_run=True`; assert `storage.get_articles()` before and after returns
      identical results
    - **Property 12: Dry-run flag prevents all Storage_Layer writes**
    - **Validates: Requirements 7.7**

- [ ] 14. Scheduler (`backend/pipeline/scheduler.py`)
  - Wrap APScheduler `BlockingScheduler` with `IntervalTrigger` using `run_interval_minutes` from
    config
  - On timeout: call `job.remove()`, log timeout error, re-add job at normal interval
  - _Requirements: 7.2, 7.5_

- [ ] 15. CLI entry point (`backend/scraper/__main__.py`)
  - Implement `python -m scraper run` (one-shot pipeline) and `python -m scraper schedule`
    (blocking scheduler) subcommands using `argparse`
  - Support `--dry-run` and `--config-path` flags for both subcommands
  - Call `setup_logging()` and `check_python_version()` at startup; catch top-level exceptions,
    log ERROR with full traceback, `sys.exit(1)`
  - _Requirements: 1.4, 7.6, 7.7, 9.3_

  - [ ] 15.1 Write unit tests for CLI invocation
    - Assert `python -m scraper run --dry-run` exits 0 with a mocked pipeline
    - Assert non-zero exit on missing config file
    - _Requirements: 1.4, 7.6_

- [ ] 16. Default feeds config (`config/feeds.yaml`)
  - Write `feeds.yaml` with all 5 pre-configured sources: `techcrunch-ai` (rss),
    `mit-tech-review-ai` (rss), `verge-ai` (rss), `arxiv-cs-ai` (arxiv, categories
    `[cs.AI, cs.LG, cs.CL, cs.CV]`), `huggingface-trending` (huggingface)
  - Include default values for `lookback_hours`, `run_interval_minutes`,
    `pipeline_timeout_seconds`, `db_path`, `json_export_path`
  - _Requirements: 2.1, 3.1, 4.1, 8.1_

- [ ] 17. AbstractClassifier stub (`backend/classifier/base.py`) — Sprint 2 seam
  - Define `AbstractClassifier` ABC with abstract `classify(self, article: Article) -> tuple[str, str]`
  - Add docstring: `"Returns (category, summary). Raises ClassificationError after retries."`
  - No implementation; this is the Sprint 2 extension point only
  - _Requirements: 10.1 (Sprint 2 seam)_

- [ ] 18. Final checkpoint — full pipeline integration
  - Ensure all tests pass, ask the user if questions arise.

---

## Sprint 2–5 Stub Tasks (optional — not for current sprint)

- [ ]\* S2.1 Implement `OpenAIClassifier` and `AnthropicClassifier` extending `AbstractClassifier`
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ]\* S2.2 Integrate `LLM_Classifier` into `Pipeline` as optional `classifier` parameter
  - _Requirements: 10.1_

- [ ]\* S3.1 Implement FastAPI app (`backend/api/main.py`) with `/articles`, `/trends`, `/sources` routers
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [ ]\* S3.2 Write integration tests for REST API endpoints (200, 400, 404)
  - _Requirements: 13.4_

- [ ]\* S4.1 Scaffold React + TypeScript frontend with Vite in `frontend/`
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ]\* S5.1 Add SQLite FTS5 virtual table and `q` parameter to `Storage_Layer.get_articles()`
  - _Requirements: 13.1_

- [ ]\* S5.2 Add Vitest + React Testing Library component tests for article feed and trend chart
  - _Requirements: 13.5_

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` with `@settings(max_examples=100)`; each test function includes
  the traceability comment `# Feature: ai-intel-dashboard, Property N: <text>`
- Checkpoints at tasks 9, 12, and 18 gate progression to the next phase
- The model MUST NOT implement tasks marked with `*` unless explicitly requested
