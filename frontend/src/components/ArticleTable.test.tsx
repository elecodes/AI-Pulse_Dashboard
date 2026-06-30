import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ArticleTable from './ArticleTable'
import type { Article } from '../types'

function makeArticle(overrides: Partial<Article> = {}): Article {
  return {
    id: '550e8400-e29b-41d4-a716-446655440000',
    title: 'Test Article',
    url: 'https://example.com/test',
    source: 'test-source',
    published_at: '2026-06-28T12:00:00Z',
    fetched_at: '2026-06-28T12:00:01Z',
    summary: 'A test article summary',
    authors: [],
    tags: [],
    category: null,
    classification_failed: false,
    raw: {},
    ...overrides,
  }
}

describe('ArticleTable', () => {
  it('renders loading state', () => {
    render(<ArticleTable articles={[]} loading={true} error={null} />)
    expect(screen.getByText('Loading articles…')).toBeInTheDocument()
  })

  it('renders error state', () => {
    render(<ArticleTable articles={[]} loading={false} error='Server error' />)
    expect(screen.getByText('Server error')).toBeInTheDocument()
  })

  it('renders empty state', () => {
    render(<ArticleTable articles={[]} loading={false} error={null} />)
    expect(screen.getByText('No articles found.')).toBeInTheDocument()
  })

  it('renders a list of articles', () => {
    const articles = [
      makeArticle({ id: '1', title: 'First Article', source: 'techcrunch-ai' }),
      makeArticle({ id: '2', title: 'Second Article', source: 'arxiv-cs-ai', category: 'LLM' }),
    ]
    render(<ArticleTable articles={articles} loading={false} error={null} />)
    expect(screen.getByText('First Article')).toBeInTheDocument()
    expect(screen.getByText('Second Article')).toBeInTheDocument()
    expect(screen.getByText('techcrunch-ai')).toBeInTheDocument()
    expect(screen.getByText('arxiv-cs-ai')).toBeInTheDocument()
  })

  it('shows uncategorized badge when category is null', () => {
    const articles = [makeArticle({ id: '1', category: null })]
    render(<ArticleTable articles={articles} loading={false} error={null} />)
    expect(screen.getByText('uncategorized')).toBeInTheDocument()
  })

  it('shows category badge when category is set', () => {
    const articles = [makeArticle({ id: '1', category: 'LLM' })]
    render(<ArticleTable articles={articles} loading={false} error={null} />)
    expect(screen.getByText('LLM')).toBeInTheDocument()
  })

  it('renders dash when published_at is null', () => {
    const articles = [makeArticle({ id: '1', published_at: null })]
    render(<ArticleTable articles={articles} loading={false} error={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
