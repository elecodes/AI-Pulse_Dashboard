# ADR 005: Frontend Architecture

**Status:** Accepted

**Context:** The dashboard UI must render a paginated article feed with filters, a stacked trend chart, and source status. It must work from 375px to 1920px viewports, handle API errors gracefully, and require zero backend changes.

**Decision:**

### Stack

| Layer | Choice | Why |
|---|---|---|
| Bundler | Vite 6 | Fastest DX, native ESM, TypeScript built-in |
| Framework | React 19 | Mature ecosystem, hooks for data fetching |
| Language | TypeScript 5.7 | Strict mode, full type coverage |
| Charts | Recharts 2.15 | Declarative, React-native, stacked bar + animations |
| Styling | Plain CSS + custom properties | Zero deps, dark theme with 6 custom properties |
| HTTP | Native `fetch` | No extra deps, typed with `ApiError` class |

### Component tree

```
<Dashboard>               ← state owner (filters, page)
  <StatsCards />          ← aggregates (total, active sources)
  <Filters />             ← category, source, date range, search
  <TrendChart />          ← stacked bar, 300ms animation
  <ArticleTable />        ← table with category badges
  <Pagination />          ← page controls
  <SourceList />          ← sources sidebar
```

### Data flow

- Filters + page state lives in `Dashboard` (single source of truth).
- `useArticles`, `useTrends`, `useSources` are custom hooks that call the API via the `api` client module.
- Each hook supports cancellation on unmount to prevent stale updates.
- Filter changes reset page to 1.

### Error handling

- `api.ts` throws `ApiError` with HTTP status and message.
- Each hook exposes `{ data, loading, error }`.
- Components render loading/error/data states — never throw.
- On API error: error message displayed inline in the relevant card; previously loaded data persists until new data arrives.

### Responsive design

- CSS Grid: `.dashboard` uses `grid-template-columns` with `auto-fit` for responsive layout.
- Sidebar collapses below content on narrow viewports.
- All components use `rem` units; min touch target 44px.
- Tested at breakpoints: 375px, 768px, 1024px, 1920px.

**Consequences:**

- Positive: Zero external UI library — no version conflicts, full control over styling.
- Positive: Hooks are ~30 lines each and trivially testable with mocked fetch.
- Positive: Error states are a first-class render path, not an afterthought.
- Negative: No SSR or SEO (not needed for a personal dashboard).
- Negative: Recharts bundle is ~470KB — worth it for stacked bar + animated transitions.
