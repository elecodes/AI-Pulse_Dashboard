import { useState, useEffect } from 'react'
import { api } from '../api'
import type { Trend } from '../types'

export function useTrends(days = 7) {
  const [data, setData] = useState<Trend[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api.getTrends(days)
      .then((res) => { if (!cancelled) setData(res) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [days])

  return { data, loading, error }
}
