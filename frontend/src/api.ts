import type { ArticlesResponse, Trend, Source } from './types';

class ApiError extends Error {
  constructor(public status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
  }
}

async function fetchJson<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v) url.searchParams.set(k, v);
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

export const api = {
  getArticles(params?: {
    page?: number;
    page_size?: number;
    category?: string;
    source?: string;
    date_from?: string;
    date_to?: string;
    q?: string;
  }): Promise<ArticlesResponse> {
    return fetchJson<ArticlesResponse>('/articles', {
      page: params?.page?.toString(),
      page_size: params?.page_size?.toString(),
      category: params?.category,
      source: params?.source,
      date_from: params?.date_from,
      date_to: params?.date_to,
      q: params?.q,
    });
  },

  getTrends(days?: number): Promise<Trend[]> {
    return fetchJson<Trend[]>('/trends', days ? { days: days.toString() } : undefined);
  },

  getSources(): Promise<Source[]> {
    return fetchJson<Source[]>('/sources');
  },
};
