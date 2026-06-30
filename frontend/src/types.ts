export interface Article {
  id: string;
  title: string;
  url: string;
  source: string;
  published_at: string | null;
  fetched_at: string;
  summary: string | null;
  authors: string[];
  tags: string[];
  category: string | null;
  classification_failed: boolean;
  raw: Record<string, unknown>;
}

export interface Trend {
  category: string | null;
  date: string;
  count: number;
}

export interface Source {
  source: string;
  last_scraped_at: string | null;
}

export interface ArticlesResponse {
  items: Article[];
  total: number;
  page: number;
  page_size: number;
}
