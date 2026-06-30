# Requirements Document

## Introduction

The AI Intelligence Dashboard is a full-stack application that aggregates AI-related content from
multiple public sources (news feeds, Hugging Face, arXiv, and AI trend sources), processes and
classifies it using LLM APIs on the backend, and presents it through an interactive React + TypeScript
frontend. The system is delivered across five sprints; Sprint 1 focuses on the Python backend
foundation: virtual environment setup, automated data extraction from public sources, normalization,
and persistent storage in a time-structured JSON/SQLite database.

## Glossary

- **Scraper**: A Python module responsible for fetching raw content from a single external source.
- **Normalizer**: The component that transforms source-specific raw records into the canonical Article schema.
- **Article**: The canonical data unit representing a single AI-related publication or news item.
- **Feed**: A configured external data source (URL + source type) consumed by a Scraper.
- **Storage_Layer**: The module responsible for persisting and querying Articles in the local database.
- **Scheduler**: The component that triggers Scraper runs on a configurable time interval.
- **Pipeline**: The end-to-end flow: Scraper → Normalizer → Storage_Layer.
- **LLM_Classifier**: The backend service (Sprint 2+) that categorizes and summarizes Articles via an LLM API.
- **REST_API**: The FastAPI application (Sprint 3+) that exposes Article data to the frontend.
- **Dashboard**: The React + TypeScript frontend (Sprint 4+) that renders Articles and analytics.
- **Category**: A topic label assigned to an Article (e.g., "NLP", "Computer Vision", "Reinforcement Learning").
- **Trend**: An aggregated view of Article volume per Category over a time window.

---

## Requirements

### Requirement 1: Python Environment Setup

**User Story:** As a developer, I want a reproducible Python virtual environment, so that the project
runs consistently across machines and contributors.

#### Acceptance Criteria

1. THE Repository SHALL contain a `requirements.txt` (or `pyproject.toml`) that pins all runtime
   and development dependencies to exact versions.
2. THE Repository SHALL contain a `README.md` section with step-by-step instructions to create the
   virtual environment, install dependencies, and run the scraper.
3. WHEN a developer follows the setup instructions on a clean machine, THE Environment SHALL install
   all dependencies without manual intervention.
4. IF a required Python version is not met, THEN THE Setup_Script SHALL print a descriptive error
   message and exit with a non-zero status code.

---

### Requirement 2: Automated News Scraping

**User Story:** As a user, I want the system to automatically fetch the latest AI news articles from
public RSS/Atom feeds and web sources, so that the dashboard always reflects current events.

#### Acceptance Criteria

1. THE Scraper SHALL support at minimum the following sources: TechCrunch AI feed, MIT Technology
   Review AI feed, and The Verge AI feed, each configurable via a feeds config file.
2. WHEN a scraping run is triggered, THE Scraper SHALL fetch articles published within the
   configurable look-back window (default: 48 hours).
3. WHEN fetching from a source, THE Scraper SHALL extract at minimum: title, URL, publication
   timestamp (ISO 8601), source name, and raw summary or body excerpt.
4. IF a source is unreachable or returns a non-200 HTTP status, THEN THE Scraper SHALL log the
   error with source name, HTTP status, and timestamp, and continue processing the remaining sources.
5. IF a source returns malformed or unparseable content, THEN THE Scraper SHALL log a warning with
   the source name and skip that source without terminating the pipeline.
6. THE Scraper SHALL deduplicate articles by URL before passing them to the Normalizer.

---

### Requirement 3: arXiv Paper Extraction

**User Story:** As a researcher, I want the system to pull the latest AI papers from arXiv, so that
I can track academic publications alongside industry news.

#### Acceptance Criteria

1. THE Scraper SHALL query the arXiv API for papers in the cs.AI, cs.LG, cs.CL, and cs.CV
   categories, with the target categories configurable via the feeds config file.
2. WHEN fetching arXiv papers, THE Scraper SHALL extract: paper ID, title, authors list, abstract,
   submission date (ISO 8601), and direct PDF URL.
3. WHEN fetching arXiv papers, THE Scraper SHALL retrieve papers submitted within the configurable
   look-back window (default: 48 hours).
4. IF the arXiv API returns an error response, THEN THE Scraper SHALL retry up to 3 times with
   exponential backoff before logging the failure and continuing.
5. THE Scraper SHALL deduplicate arXiv papers by paper ID before passing them to the Normalizer.

---

### Requirement 4: Hugging Face Feed Extraction

**User Story:** As a developer, I want the system to capture trending models and papers from
Hugging Face, so that I can monitor the ML community's activity.

#### Acceptance Criteria

1. THE Scraper SHALL fetch trending models and papers from the Hugging Face public API or RSS feed,
   with the endpoint configurable via the feeds config file.
2. WHEN fetching from Hugging Face, THE Scraper SHALL extract at minimum: name/title, URL, description
   or excerpt, and the fetch timestamp (ISO 8601) as publication date when no native date is available.
3. IF the Hugging Face endpoint is unreachable, THEN THE Scraper SHALL log the error and continue
   the pipeline without terminating.
4. THE Scraper SHALL deduplicate Hugging Face items by URL before passing them to the Normalizer.

---

### Requirement 5: Data Normalization

**User Story:** As a developer, I want all scraped content normalized into a single schema, so that
downstream components can process data uniformly regardless of source.

#### Acceptance Criteria

1. THE Normalizer SHALL transform every raw record into an Article with these fields: `id` (UUID v4),
   `title` (string), `url` (string), `source` (string), `published_at` (ISO 8601 string),
   `fetched_at` (ISO 8601 string), `summary` (string or null), `authors` (list of strings, may be
   empty), `tags` (list of strings, initially empty), `category` (string or null), `raw` (original
   source payload as a dict).
2. WHEN a raw record is missing a required field (`title`, `url`, or `published_at`), THEN THE
   Normalizer SHALL discard the record and log a warning with the source name and missing fields.
3. THE Normalizer SHALL parse and normalize all timestamps to UTC ISO 8601 format
   (`YYYY-MM-DDTHH:MM:SSZ`).
4. IF a timestamp cannot be parsed, THEN THE Normalizer SHALL set `published_at` to null, log a
   warning, and retain the record.
5. THE Normalizer SHALL truncate `summary` fields that exceed 2000 characters to exactly 2000
   characters, preserving valid UTF-8 boundaries.
6. THE Pretty_Printer SHALL serialize any Article object back to a valid JSON string.
7. FOR ALL valid Article objects, serializing then deserializing then serializing SHALL produce an
   identical JSON string (round-trip property).

---

### Requirement 6: Persistent Storage

**User Story:** As a developer, I want scraped articles stored in a local time-structured database,
so that historical data is preserved across scraper runs and queryable by date.

#### Acceptance Criteria

1. THE Storage_Layer SHALL persist Articles in a SQLite database file with a configurable path
   (default: `data/articles.db`).
2. THE Storage_Layer SHALL also export a JSON snapshot of all Articles to a configurable path
   (default: `data/articles.json`) after every successful pipeline run.
3. THE Storage_Layer SHALL enforce a unique constraint on `url`; WHEN an Article with a duplicate
   URL is inserted, THE Storage_Layer SHALL update the existing record's `fetched_at` and `raw`
   fields and skip re-insertion of unchanged fields.
4. THE Storage_Layer SHALL index Articles by `published_at` date to support time-range queries.
5. WHEN queried by date range, THE Storage_Layer SHALL return all Articles whose `published_at` falls
   within the inclusive start and end timestamps, ordered by `published_at` descending.
6. THE Storage_Layer SHALL record each pipeline run in a `runs` table with: run ID, start time,
   end time, articles fetched count, articles inserted count, and status (success/failure).
7. IF the database file does not exist at startup, THEN THE Storage_Layer SHALL create the file and
   initialize the schema automatically.
8. IF a write operation fails, THEN THE Storage_Layer SHALL roll back the transaction, log the error,
   and raise an exception to the caller.

---

### Requirement 7: Pipeline Orchestration and Scheduling

**User Story:** As an operator, I want the scraping pipeline to run automatically on a schedule, so
that data is refreshed without manual intervention.

#### Acceptance Criteria

1. THE Pipeline SHALL execute the full sequence: Scraper → Normalizer → Storage_Layer as a single
   atomic run.
2. THE Scheduler SHALL support a configurable run interval (default: every 60 minutes) via an
   environment variable or config file.
3. WHEN a pipeline run starts, THE Pipeline SHALL log the start time and source list being scraped.
4. WHEN a pipeline run completes, THE Pipeline SHALL log the total articles fetched, inserted,
   deduplicated, and discarded, along with total duration in seconds.
5. IF a pipeline run exceeds a configurable timeout (default: 300 seconds), THEN THE Scheduler SHALL
   terminate the run, log a timeout error, and schedule the next run at the normal interval.
6. THE Pipeline SHALL be executable as a one-shot run via a CLI command (`python -m scraper run`)
   in addition to scheduled mode.
7. WHERE a `--dry-run` flag is provided, THE Pipeline SHALL execute all scraping and normalization
   steps but SHALL NOT write any data to the Storage_Layer.

---

### Requirement 8: Configuration Management

**User Story:** As a developer, I want all sources and parameters configurable without code changes,
so that adding or modifying feeds requires only a config file update.

#### Acceptance Criteria

1. THE System SHALL load feed definitions from a YAML or JSON config file at a configurable path
   (default: `config/feeds.yaml`).
2. WHEN the config file is missing or unparseable, THEN THE System SHALL log a descriptive error
   and exit with a non-zero status code.
3. THE System SHALL support overriding any config value via environment variables following the
   pattern `AIID_<SETTING_NAME>` (e.g., `AIID_LOOKBACK_HOURS=24`).
4. THE Config_Loader SHALL parse the config file into a typed configuration object and validate
   required fields on startup.
5. IF a required config field is absent, THEN THE Config_Loader SHALL raise a descriptive
   `ConfigurationError` before any scraping begins.

---

### Requirement 9: Observability and Logging

**User Story:** As a developer, I want structured logs from every pipeline component, so that I can
diagnose failures and monitor scraper health.

#### Acceptance Criteria

1. THE System SHALL emit structured logs in JSON format when the `LOG_FORMAT=json` environment
   variable is set, and human-readable format otherwise.
2. THE System SHALL support log levels DEBUG, INFO, WARNING, and ERROR, configurable via the
   `LOG_LEVEL` environment variable (default: INFO).
3. WHEN an unhandled exception propagates to the top-level pipeline runner, THE System SHALL log
   the full stack trace at ERROR level and exit with a non-zero status code.
4. THE System SHALL write logs to stdout by default, with optional file output configurable via
   `LOG_FILE` environment variable.

---

### Requirement 10: LLM-Based Classification and Summarization (Sprint 2)

**User Story:** As a user, I want each article automatically categorized and summarized by an LLM,
so that I can quickly scan topics without reading full content.

#### Acceptance Criteria

1. THE LLM_Classifier SHALL accept an Article and return a Category label and a summary of at most
   150 words.
2. THE LLM_Classifier SHALL support at minimum OpenAI and Anthropic API providers, selectable via
   config.
3. WHEN the LLM API returns an error, THE LLM_Classifier SHALL retry up to 3 times with exponential
   backoff before marking the Article as `classification_failed`.
4. THE LLM_Classifier SHALL update the Article's `category` and `summary` fields in the
   Storage_Layer upon successful classification.
5. THE LLM_Classifier SHALL process Articles in batches of configurable size (default: 20) to
   respect API rate limits.

---

### Requirement 11: REST API (Sprint 3)

**User Story:** As a frontend developer, I want a REST API that exposes paginated article data and
trend analytics, so that the dashboard can render dynamic content.

#### Acceptance Criteria

1. THE REST_API SHALL expose `GET /articles` with query parameters: `page`, `page_size`, `category`,
   `source`, `date_from`, `date_to`.
2. THE REST_API SHALL expose `GET /articles/{id}` returning a single Article or 404.
3. THE REST_API SHALL expose `GET /trends` returning article volume per Category per day for a
   configurable time window.
4. THE REST_API SHALL expose `GET /sources` returning the list of configured feed sources and their
   last successful scrape timestamp.
5. WHEN a request includes invalid query parameters, THE REST_API SHALL return HTTP 400 with a
   JSON error body describing the invalid fields.
6. THE REST_API SHALL include OpenAPI documentation auto-generated at `/docs`.

---

### Requirement 12: Frontend Dashboard (Sprint 4)

**User Story:** As an end user, I want an interactive web dashboard that displays articles and
trends, so that I can explore AI developments at a glance.

#### Acceptance Criteria

1. THE Dashboard SHALL display a paginated article feed with title, source, date, category badge,
   and summary for each Article.
2. THE Dashboard SHALL provide filters for category, source, and date range that update the feed
   without full page reload.
3. THE Dashboard SHALL render a trend chart showing article volume by category over the selected
   time window.
4. WHEN the API is unreachable, THE Dashboard SHALL display a non-blocking error banner and retain
   the last successfully loaded data.
5. THE Dashboard SHALL be responsive and usable on viewport widths from 375px to 1920px.

---

### Requirement 13: Advanced UI/UX and Testing (Sprint 5)

**User Story:** As a user, I want polished filtering, search, and trend visualization, so that I
can efficiently navigate large volumes of AI content.

#### Acceptance Criteria

1. THE Dashboard SHALL provide a full-text search input that filters the visible article list
   client-side within 100ms for datasets up to 1000 articles.
2. THE Dashboard SHALL animate trend chart transitions when filters change, completing within 300ms.
3. THE System SHALL include unit tests for all Scraper, Normalizer, and Storage_Layer modules with
   a minimum line coverage of 80%.
4. THE System SHALL include integration tests for each REST API endpoint covering success, 400, and
   404 response codes.
5. THE Dashboard SHALL include component tests for the article feed and trend chart components.
