import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import TrendChart from './TrendChart'

describe('TrendChart', () => {
  it('renders loading state', () => {
    render(<TrendChart data={null} loading={true} error={null} />)
    expect(screen.getByText('Loading chart…')).toBeInTheDocument()
  })

  it('renders error state', () => {
    render(<TrendChart data={null} loading={false} error='API Error' />)
    expect(screen.getByText('API Error')).toBeInTheDocument()
  })

  it('renders empty state when data is empty array', () => {
    render(<TrendChart data={[]} loading={false} error={null} />)
    expect(screen.getByText('No trend data available.')).toBeInTheDocument()
  })

  it('renders chart title with trend data without crashing', () => {
    const data = [
      { category: 'LLM', date: '2026-06-28T00:00:00Z', count: 5 },
      { category: 'Computer Vision', date: '2026-06-28T00:00:00Z', count: 2 },
    ]
    const { container } = render(<TrendChart data={data} loading={false} error={null} />)
    expect(screen.getByText('Article Volume by Category')).toBeInTheDocument()
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })

  it('handles null category as Unknown', () => {
    const data = [
      { category: null, date: '2026-06-28T00:00:00Z', count: 1 },
    ]
    const { container } = render(<TrendChart data={data} loading={false} error={null} />)
    expect(screen.getByText('Article Volume by Category')).toBeInTheDocument()
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })
})
