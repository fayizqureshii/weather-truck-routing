import type { RouteOption } from './types'

function haversineMiles(a: [number, number], b: [number, number]): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b[0] - a[0])
  const dLon = toRad(b[1] - a[1])
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2
  return 2 * 3958.7613 * Math.asin(Math.sqrt(h))
}

export interface RouteTrack {
  route: RouteOption
  cumMiles: number[]
}

export function makeTrack(route: RouteOption): RouteTrack {
  const cumMiles = [0]
  for (let i = 1; i < route.geometry.length; i++) {
    cumMiles.push(cumMiles[i - 1] + haversineMiles(route.geometry[i - 1], route.geometry[i]))
  }
  return { route, cumMiles }
}

export type TruckState = 'not-departed' | 'en-route' | 'arrived'

/**
 * Where the truck is `hours` after departure. Time -> mile comes from the checkpoint ETAs
 * (which follow the routing engine's per-segment speeds); mile -> position follows the road.
 */
export function positionAt(track: RouteTrack, hours: number): { lngLat: [number, number]; state: TruckState } {
  const { route, cumMiles } = track
  const cps = route.checkpoints
  const last = cps[cps.length - 1]
  if (hours <= 0) return { lngLat: [route.geometry[0][1], route.geometry[0][0]], state: 'not-departed' }
  if (hours >= last.hours_from_departure) {
    const end = route.geometry[route.geometry.length - 1]
    return { lngLat: [end[1], end[0]], state: 'arrived' }
  }

  let i = 0
  while (i < cps.length - 2 && cps[i + 1].hours_from_departure < hours) i++
  const a = cps[i]
  const b = cps[i + 1]
  const span = b.hours_from_departure - a.hours_from_departure
  const mile = a.mile + (span > 0 ? ((hours - a.hours_from_departure) / span) * (b.mile - a.mile) : 0)

  // Geometry is simplified, so scale route miles onto its (slightly shorter) length.
  const target = (mile / route.distance_miles) * cumMiles[cumMiles.length - 1]
  let j = 0
  while (j < cumMiles.length - 2 && cumMiles[j + 1] < target) j++
  const seg = cumMiles[j + 1] - cumMiles[j]
  const t = seg > 0 ? (target - cumMiles[j]) / seg : 0
  const [lat0, lon0] = route.geometry[j]
  const [lat1, lon1] = route.geometry[j + 1]
  return { lngLat: [lon0 + (lon1 - lon0) * t, lat0 + (lat1 - lat0) * t], state: 'en-route' }
}
