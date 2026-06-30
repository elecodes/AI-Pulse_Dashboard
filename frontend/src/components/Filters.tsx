import { type FormEvent, useCallback, useState, useEffect, useRef } from 'react'
import type { Source } from '../types'
import './Filters.css'

interface FiltersProps {
  categories: string[]
  sources: Source[]
  filters: {
    category: string
    source: string
    date_from: string
    date_to: string
    q: string
  }
  onChange: (filters: { category: string; source: string; date_from: string; date_to: string; q: string }) => void
}

export default function Filters({ categories, sources, filters, onChange }: FiltersProps) {
  const [searchInput, setSearchInput] = useState(filters.q)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setSearchInput(filters.q)
  }, [filters.q])

  const handleDebouncedSearch = useCallback(
    (value: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        onChange({ ...filters, q: value })
      }, 300)
    },
    [filters, onChange],
  )

  const handleChange = useCallback(
    (field: string, value: string) => {
      if (field === 'q') {
        setSearchInput(value)
        handleDebouncedSearch(value)
        return
      }
      onChange({ ...filters, [field]: value })
    },
    [filters, onChange, handleDebouncedSearch],
  )

  const handleReset = useCallback(
    (e: FormEvent) => {
      e.preventDefault()
      setSearchInput('')
      onChange({ category: '', source: '', date_from: '', date_to: '', q: '' })
    },
    [onChange],
  )

  return (
    <div className="card">
      <div className="card-title">Filters</div>
      <div className="filters-row">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => handleChange('q', e.target.value)}
          placeholder="Search articles…"
          aria-label="Search articles"
          className="search-input"
        />

        <select
          value={filters.category}
          onChange={(e) => handleChange('category', e.target.value)}
          aria-label="Filter by category"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <select
          value={filters.source}
          onChange={(e) => handleChange('source', e.target.value)}
          aria-label="Filter by source"
        >
          <option value="">All Sources</option>
          {sources.map((s) => (
            <option key={s.source} value={s.source}>{s.source}</option>
          ))}
        </select>

        <input
          type="date"
          value={filters.date_from}
          onChange={(e) => handleChange('date_from', e.target.value)}
          aria-label="From date"
          placeholder="From"
        />

        <input
          type="date"
          value={filters.date_to}
          onChange={(e) => handleChange('date_to', e.target.value)}
          aria-label="To date"
          placeholder="To"
        />

        <button className="btn btn-secondary" onClick={handleReset}>
          Reset
        </button>
      </div>
    </div>
  )
}
