export interface Place {
  name: string
  lat: number
  lon: number
}

export type RiskLevel = 0 | 1 | 2 | 3 | 4

export interface Weather {
  wind_mph: number
  gust_mph: number
  rain_in_hr: number
  snow_in_hr: number
  temp_f: number
  weather_code: number
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  hours_from_departure: number
  weather: Weather
  risk: {
    level: RiskLevel
    label: string
    components: { wind: RiskLevel; rain: RiskLevel; snow: RiskLevel }
    reasons: string[]
  }
}

export interface RouteOption {
  id: string
  name: string
  rank: number
  via: string
  distance_miles: number
  duration_hours: number
  arrival: string
  risk: {
    miles_by_level: Record<string, number>
    average_risk: number
    max_level: RiskLevel
    max_label: string
  }
  geometry: [number, number][] // [lat, lon]
  checkpoints: Checkpoint[]
}

export interface HeatmapGrid {
  west: number
  east: number
  north: number
  south: number
  cols: number
  rows: number
  cells: [number, number, number, number][] // [row, col, lat, lon]
}

export interface Plan {
  origin: Place
  destination: Place
  departure: string
  load_lb: number
  interval_miles: number
  recommended: string
  recommendation_reason: string
  routes: RouteOption[]
  heatmap_grid: HeatmapGrid
}

export interface Heatmap {
  start: string
  hours: number
  cells: [number, number][]
  scores: number[][] // [hour][cell], 0–4 continuous
  wind_mph: number[][]
  rain_in_hr: number[][]
  snow_in_hr: number[][]
}

export interface PlanInput {
  origin: Place | string
  destination: Place | string
  departure: string
  load_lb: number
  interval_miles: 10 | 25 | 50
}
