import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from 'recharts'
import type { Trend } from '../types'
import './TrendChart.css'

const COLORS = [
  '#38bdf8',
  '#a78bfa',
  '#22c55e',
  '#eab308',
  '#ef4444',
  '#f97316',
  '#06b6d4',
  '#ec4899',
]

interface TrendChartProps {
  data: Trend[] | null
  loading: boolean
  error: string | null
}

export default function TrendChart({ data, loading, error }: TrendChartProps) {
  type ChartRow = {
    date: string
    [category: string]: string | number
  }

  const chartData = useMemo(() => {
    if (!data || data.length === 0) return []

    const dateMap = new Map<string, ChartRow>()

    for (const d of data) {
      const key = d.date.slice(0, 10)
      if (!dateMap.has(key)) {
        dateMap.set(key, { date: key })
      }
      const row = dateMap.get(key)!
      const cat = d.category ?? 'Unknown'
      row[cat] = (typeof row[cat] === 'number' ? row[cat] : 0) + d.count
    }

    return Array.from(dateMap.values()).sort(
      (a, b) => (a.date as string).localeCompare(b.date as string),
    )
  }, [data])

  const categories = useMemo(() => {
    if (!data) return []
    return [...new Set(data.map((d) => d.category ?? 'Unknown'))]
  }, [data])

  if (loading) {
    return (
      <div className="card">
        <div className="card-title">Article Volume by Category</div>
        <div className="chart-placeholder">Loading chart…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card">
        <div className="card-title">Article Volume by Category</div>
        <div className="chart-placeholder chart-error">{error}</div>
      </div>
    )
  }

  if (chartData.length === 0) {
    return (
      <div className="card">
        <div className="card-title">Article Volume by Category</div>
        <div className="chart-placeholder">No trend data available.</div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-title">Article Volume by Category</div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} key={chartData.length + '-' + categories.length}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 6,
              fontSize: 12,
            }}
            labelStyle={{ color: '#f1f5f9' }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {categories.map((cat, i) => (
            <Bar
              key={cat}
              dataKey={cat}
              stackId="a"
              fill={COLORS[i % COLORS.length]}
              animationDuration={300}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
