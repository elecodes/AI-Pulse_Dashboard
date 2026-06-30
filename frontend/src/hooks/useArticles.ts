import { useState, useEffect } from 'react'
import { api } from '../api'
import type { ArticlesResponse } from '../types'

interface ArticleFilters {
  page: number
  page_size: number
  category?: string
  source?: string
  date_from?: string
  date_to?: string
  q?: string
}

export function useArticles(filters: ArticleFilters) {
  const [data, setData] = useState<ArticlesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api.getArticles(filters)
      .then((res) => { if (!cancelled) setData(res) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [
    filters.page,
    filters.page_size,
    filters.category,
    filters.source,
    filters.date_from,
    filters.date_to,
    filters.q,
  ])

  return { data, loading, error }
}
