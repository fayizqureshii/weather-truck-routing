import type { RiskLevel } from './types'

export const RISK_LABELS = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'] as const

export const RISK_COLORS: Record<RiskLevel, string> = {
  0: '#2f9e5b',
  1: '#e0b100',
  2: '#f07c1b',
  3: '#d62828',
  4: '#6a1b9a',
}

export const ROUTE_COLORS: Record<string, string> = {
  'Route A': '#2563eb',
  'Route B': '#0891b2',
  'Route C': '#475569',
}

// RGB stops for the continuous 0–4 heatmap score (same hues as the levels).
const SCORE_STOPS: [number, [number, number, number]][] = [
  [0, [47, 158, 91]],
  [1, [224, 177, 0]],
  [2, [240, 124, 27]],
  [3, [214, 40, 40]],
  [4, [106, 27, 154]],
]

/** RGBA for a heatmap score. Calm weather stays faint so hazards stand out. */
export function scoreToRgba(score: number): [number, number, number, number] {
  const s = Math.min(Math.max(score, 0), 4)
  let i = 0
  while (i < SCORE_STOPS.length - 2 && s > SCORE_STOPS[i + 1][0]) i++
  const [s0, c0] = SCORE_STOPS[i]
  const [s1, c1] = SCORE_STOPS[i + 1]
  const t = (s - s0) / (s1 - s0)
  const rgb = c0.map((v, k) => Math.round(v + (c1[k] - v) * t))
  const alpha = Math.round(255 * (0.12 + 0.6 * Math.min(s / 2.5, 1)))
  return [rgb[0], rgb[1], rgb[2], alpha]
}
