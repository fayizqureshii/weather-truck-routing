import type { Heatmap, HeatmapGrid, Place, Plan, PlanInput } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await resp.json().catch(() => null)
  if (!resp.ok) {
    throw new Error(formatError(body) ?? `Request failed (${resp.status})`)
  }
  return body as T
}

function formatError(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  if ('error' in body && typeof body.error === 'string') return body.error
  // DRF validation errors: { field: ["message"] }
  const parts = Object.entries(body as Record<string, unknown>).map(([field, msgs]) => {
    const text = Array.isArray(msgs) ? msgs.join(' ') : String(msgs)
    return field === 'non_field_errors' ? text : `${field.replace('_', ' ')}: ${text}`
  })
  return parts.join(' ') || null
}

export function geocode(q: string, signal?: AbortSignal): Promise<{ results: Place[] }> {
  return request(`/api/geocode?q=${encodeURIComponent(q)}`, { signal })
}

export function planTrip(input: PlanInput, signal?: AbortSignal): Promise<Plan> {
  return request('/api/plan', { method: 'POST', body: JSON.stringify(input), signal })
}

export function fetchHeatmap(
  grid: HeatmapGrid,
  start: string,
  loadLb: number,
  signal?: AbortSignal,
): Promise<Heatmap> {
  return request('/api/heatmap', {
    method: 'POST',
    body: JSON.stringify({
      cells: grid.cells.map(([, , lat, lon]) => [lat, lon]),
      start,
      load_lb: loadLb,
    }),
    signal,
  })
}
