import { useState, useMemo, useCallback } from 'react'
import { useArticles } from '../hooks/useArticles'
import { useTrends } from '../hooks/useTrends'
import { useSources } from '../hooks/useSources'
import StatsCards from '../components/StatsCards'
import Filters from '../components/Filters'
import ArticleTable from '../components/ArticleTable'
import Pagination from '../components/Pagination'
import TrendChart from '../components/TrendChart'
import SourceList from '../components/SourceList'

const PAGE_SIZE = 20

export default function Dashboard() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState({
    category: '',
    source: '',
    date_from: '',
    date_to: '',
    q: '',
  })

  const { data: articlesData, loading: articlesLoading, error: articlesError } = useArticles({
    page,
    page_size: PAGE_SIZE,
    category: filters.category || undefined,
    source: filters.source || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    q: filters.q || undefined,
  })

  const { data: trends, loading: trendsLoading, error: trendsError } = useTrends(7)
  const { data: sources, loading: sourcesLoading, error: sourcesError } = useSources()

  const categories = useMemo(() => {
    if (!trends) return []
    const cats = new Set(trends.map((t) => t.category).filter(Boolean) as string[])
    return [...cats].sort()
  }, [trends])

  const handleFilterChange = useCallback(
    (newFilters: { category: string; source: string; date_from: string; date_to: string; q: string }) => {
      setFilters(newFilters)
      setPage(1)
    },
    [],
  )

  return (
    <>
      <header className="app-header">
        <div className="logo">AI</div>
        <h1>Intelligence Dashboard</h1>
      </header>

      <div className="dashboard">
        <div className="dashboard-main">
          <StatsCards
            articles={articlesData}
            sources={sources ?? null}
            trends={trends ?? null}
          />

          <Filters
            categories={categories}
            sources={sources ?? []}
            filters={filters}
            onChange={handleFilterChange}
          />

          <TrendChart data={trends ?? null} loading={trendsLoading} error={trendsError} />

          <ArticleTable
            articles={articlesData?.items ?? []}
            loading={articlesLoading}
            error={articlesError}
          />

          {articlesData && (
            <Pagination
              page={articlesData.page}
              pageSize={articlesData.page_size}
              total={articlesData.total}
              onChange={setPage}
            />
          )}
        </div>

        <aside className="dashboard-sidebar">
          <SourceList
            sources={sources ?? null}
            loading={sourcesLoading}
            error={sourcesError}
          />
        </aside>
      </div>
    </>
  )
}
