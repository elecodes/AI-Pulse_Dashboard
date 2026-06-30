import './Pagination.css'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}

export default function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize)

  if (totalPages <= 1) return null

  const pages: number[] = []
  const start = Math.max(1, page - 2)
  const end = Math.min(totalPages, page + 2)

  for (let i = start; i <= end; i++) {
    pages.push(i)
  }

  return (
    <div className="pagination">
      <span className="pagination-info">
        {total} article{total !== 1 ? 's' : ''}
      </span>

      <div className="pagination-controls">
        <button
          className="pagination-btn"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          ‹ Prev
        </button>

        {start > 1 && (
          <>
            <button className="pagination-btn" onClick={() => onChange(1)}>1</button>
            {start > 2 && <span className="pagination-ellipsis">…</span>}
          </>
        )}

        {pages.map((p) => (
          <button
            key={p}
            className={`pagination-btn${p === page ? ' pagination-btn--active' : ''}`}
            onClick={() => onChange(p)}
          >
            {p}
          </button>
        ))}

        {end < totalPages && (
          <>
            {end < totalPages - 1 && <span className="pagination-ellipsis">…</span>}
            <button className="pagination-btn" onClick={() => onChange(totalPages)}>
              {totalPages}
            </button>
          </>
        )}

        <button
          className="pagination-btn"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
        >
          Next ›
        </button>
      </div>
    </div>
  )
}
