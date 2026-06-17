import type { OverlapResult, TitleHit } from './types'

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal })
  if (!res.ok) {
    let detail: string | undefined
    try {
      const body = (await res.json()) as { detail?: string }
      detail = body?.detail
    } catch {
      // ignore: response not JSON
    }
    throw new Error(detail ?? `Request failed: ${res.status} ${res.statusText}`)
  }
  return (await res.json()) as T
}

export function searchTitles(
  query: string,
  signal?: AbortSignal,
  limit = 8,
): Promise<TitleHit[]> {
  const u = new URL('/api/search', window.location.origin)
  u.searchParams.set('q', query)
  u.searchParams.set('limit', String(limit))
  return getJson<TitleHit[]>(u.pathname + u.search, signal)
}

export function getOverlap(
  ids: string[],
  signal?: AbortSignal,
): Promise<OverlapResult> {
  const u = new URL('/api/overlap', window.location.origin)
  for (const id of ids) {
    u.searchParams.append('ids', id)
  }
  return getJson<OverlapResult>(u.pathname + u.search, signal)
}
