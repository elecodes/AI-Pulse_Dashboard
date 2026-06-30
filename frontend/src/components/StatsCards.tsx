import type { ArticlesResponse, Source, Trend } from '../types'
import './StatsCards.css'

interface StatsCardsProps {
  articles: ArticlesResponse | null
  sources: Source[] | null
  trends: Trend[] | null
}

export default function StatsCards({ articles, sources, trends }: StatsCardsProps) {
  const articleCount = articles?.total ?? 0
  const sourceCount = sources?.length ?? 0

  const trendDays = trends
    ? new Set(trends.map((t) => t.date)).size
    : 0

  const stats = [
    { label: 'Total Articles', value: articleCount.toLocaleString() },
    { label: 'Sources', value: sourceCount.toLocaleString() },
    { label: 'Days of Data', value: trendDays.toLocaleString() },
    { label: 'Categories', value: trends ? new Set(trends.map((t) => t.category)).size.toLocaleString() : '—' },
  ]

  return (
    <div className="stats-grid">
      {stats.map((s) => (
        <div key={s.label} className="card stat-card">
          <div className="stat-label">{s.label}</div>
          <div className="stat-value">{s.value}</div>
        </div>
      ))}
    </div>
  )
}
