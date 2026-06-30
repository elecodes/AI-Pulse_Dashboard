# ADR 004: REST API Design

**Status:** Accepted

**Context:** The frontend needs a queryable API for articles, trends, and source metadata. The API must support filtering, pagination, full-text search, and produce OpenAPI documentation automatically.

**Decision:**

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/articles` | Paginated article list with filters |
| GET | `/articles/{id}` | Single article by UUID |
| GET | `/trends` | Article volume per category per day |
| GET | `/sources` | Active sources with last scrape timestamp |

### Pagination

```json
GET /articles?page=1&page_size=20

{
  "items": [...],
  "total": 142,
  "page": 1,
  "page_size": 20
}
```

Offset-based pagination (cursor is overkill for <10K articles).

### Search

FTS5 via SQLite virtual table:

```sql
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title, summary,
    content='articles',
    tokenize='porter unicode61'
);
```

- Query param `?q=llm+agents` triggers a FTS5 MATCH on `title` and `summary`.
- Index rebuilt automatically after each `save_batch()`.
- Query sanitized: each term wrapped in double quotes to avoid FTS5 syntax injection.

### Error responses

All validation errors return HTTP 400 instead of FastAPI's default 422:

```json
{
  "detail": [{"loc": ["query", "page"], "msg": "Input should be >= 1", ...}]
}
```

### OpenAPI

Auto-generated at `/docs` via FastAPI's built-in OpenAPI integration. No manual spec maintenance.

**Consequences:**

- Positive: Frontend dev can explore the API at `/docs` without reading backend code.
- Positive: FTS5 search is sub-5ms even on 10K articles.
- Negative: FTS5 index must be rebuilt on every write — acceptable for <1 write/second.
