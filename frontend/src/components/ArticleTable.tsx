import type { Article } from '../types'
import './ArticleTable.css'

interface ArticleTableProps {
  articles: Article[]
  loading: boolean
  error: string | null
}

export default function ArticleTable({ articles, loading, error }: ArticleTableProps) {
  if (loading) {
    return (
      <div className="card">
        <div className="card-title">Articles</div>
        <div className="table-status">Loading articles…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div className="card-title">Articles</div>
        <div className="table-status table-error">{error}</div>
      </div>
    )
  }

  if (articles.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Articles</div>
        <div className="table-status">No articles found.</div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-title">Articles</div>
      <div className="table-wrapper">
        <table className="article-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Source</th>
              <th>Category</th>
              <th>Published</th>
            </tr>
          </thead>
          <tbody>
            {articles.map((a) => (
              <tr key={a.id}>
                <td>
                  <a href={a.url} target="_blank" rel="noopener noreferrer" className="article-title">
                    {a.title}
                  </a>
                </td>
                <td>
                  <span className="badge badge-source">{a.source}</span>
                </td>
                <td>
                  {a.category ? (
                    <span className="badge badge-category">{a.category}</span>
                  ) : (
                    <span className="badge badge-muted">uncategorized</span>
                  )}
                </td>
                <td className="cell-date">
                  {a.published_at
                    ? new Date(a.published_at).toLocaleDateString()
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
