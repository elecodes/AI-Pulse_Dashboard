import type { Source } from '../types'
import './SourceList.css'

interface SourceListProps {
  sources: Source[] | null
  loading: boolean
  error: string | null
}

export default function SourceList({ sources, loading, error }: SourceListProps) {
  if (loading) {
    return (
      <div className="card">
        <div className="card-title">Sources</div>
        <div className="sources-status">Loading sources…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div className="card-title">Sources</div>
        <div className="sources-status sources-error">{error}</div>
      </div>
    )
  }

  if (!sources || sources.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Sources</div>
        <div className="sources-status">No sources found.</div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-title">Sources</div>
      <ul className="source-list">
        {sources.map((s) => (
          <li key={s.source} className="source-item">
            <div className="source-name">{s.source}</div>
            <div className="source-meta">
              {s.last_scraped_at
                ? `Scraped ${new Date(s.last_scraped_at).toLocaleDateString()}`
                : 'Not yet scraped'}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
