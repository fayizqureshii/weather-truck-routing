import maplibregl, { type GeoJSONSource, type ImageSource, type MapLayerMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef } from 'react'
import { cellAt, type HeatmapFrames } from '../heatmap'
import { formatDateTime } from '../format'
import { makeTrack, positionAt } from '../position'
import { RISK_COLORS, RISK_LABELS, ROUTE_COLORS } from '../risk'
import type { Checkpoint, Heatmap, Plan } from '../types'

const STYLE_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'

interface Props {
  plan: Plan | null
  selectedRoute: string | null
  onSelectRoute: (id: string) => void
  heatmap: Heatmap | null
  frames: HeatmapFrames | null
  hour: number
  showHeatmap: boolean
  focus: Checkpoint | null
}

const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

function checkpointPopupHtml(routeName: string, cp: Checkpoint): string {
  const w = cp.weather
  const reasons = cp.risk.reasons.length ? cp.risk.reasons.map((r) => `<li>${r}</li>`).join('') : '<li>No hazards</li>'
  return `
    <div class="popup">
      <div class="popup-title">${routeName} · mile ${Math.round(cp.mile)}</div>
      <div class="popup-risk" style="background:${RISK_COLORS[cp.risk.level]}">${cp.risk.label}</div>
      <div class="popup-row"><span>ETA</span><b>${formatDateTime(cp.eta)}</b></div>
      <div class="popup-row"><span>Wind</span><b>${w.wind_mph.toFixed(0)} mph (gusts ${w.gust_mph.toFixed(0)})</b></div>
      <div class="popup-row"><span>Rain</span><b>${w.rain_in_hr.toFixed(2)} in/hr</b></div>
      <div class="popup-row"><span>Snow</span><b>${w.snow_in_hr.toFixed(2)} in/hr</b></div>
      <div class="popup-row"><span>Temp</span><b>${w.temp_f.toFixed(0)}°F</b></div>
      <ul class="popup-reasons">${reasons}</ul>
    </div>`
}

export function MapView({ plan, selectedRoute, onSelectRoute, heatmap, frames, hour, showHeatmap, focus }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const readyRef = useRef<Promise<void> | null>(null)
  const truckRef = useRef<maplibregl.Marker | null>(null)
  const endpointMarkers = useRef<maplibregl.Marker[]>([])
  const popupRef = useRef<maplibregl.Popup | null>(null)
  const hoverPopupRef = useRef<maplibregl.Popup | null>(null)
  // Latest values for map event handlers registered once.
  const latest = useRef({ plan, heatmap, frames, hour, showHeatmap, onSelectRoute })
  latest.current = { plan, heatmap, frames, hour, showHeatmap, onSelectRoute }

  // --- Map setup (once) ---
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current!,
      style: STYLE_URL,
      center: [-96, 38.5],
      zoom: 3.6,
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    mapRef.current = map

    readyRef.current = new Promise((resolve) => {
      map.on('load', () => {
        const firstLabel = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
        map.addSource('heatmap', {
          type: 'image',
          url: 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==',
          coordinates: [[-1, 1], [1, 1], [1, -1], [-1, -1]],
        })
        map.addLayer(
          {
            id: 'heatmap',
            type: 'raster',
            source: 'heatmap',
            layout: { visibility: 'none' },
            paint: { 'raster-resampling': 'linear', 'raster-opacity': 0.85, 'raster-fade-duration': 0 },
          },
          firstLabel,
        )

        map.addSource('routes', { type: 'geojson', data: empty })
        map.addLayer({
          id: 'routes-casing',
          type: 'line',
          source: 'routes',
          filter: ['==', ['get', 'selected'], true],
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': '#ffffff', 'line-width': 10 },
        })
        map.addLayer({
          id: 'routes',
          type: 'line',
          source: 'routes',
          layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['case', ['get', 'selected'], 1, 0] },
          paint: {
            'line-color': ['get', 'color'],
            'line-width': ['case', ['get', 'selected'], 6, 4],
            'line-opacity': ['case', ['get', 'selected'], 1, 0.55],
          },
        })

        map.addSource('checkpoints', { type: 'geojson', data: empty })
        map.addLayer({
          id: 'checkpoints',
          type: 'circle',
          source: 'checkpoints',
          layout: { 'circle-sort-key': ['+', ['case', ['get', 'selected'], 10, 0], ['get', 'level']] },
          paint: {
            'circle-color': ['get', 'color'],
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, ['case', ['get', 'selected'], 4.5, 2.5], 9, ['case', ['get', 'selected'], 8, 4.5]],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': ['case', ['get', 'selected'], 1.5, 0.75],
            'circle-opacity': ['case', ['get', 'selected'], 1, 0.7],
          },
        })
        resolve()
      })
    })

    map.on('click', 'routes', (e: MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.id
      if (id) latest.current.onSelectRoute(id)
    })
    map.on('click', 'checkpoints', (e: MapLayerMouseEvent) => {
      const f = e.features?.[0]
      const p = latest.current.plan
      if (!f || !p) return
      const route = p.routes.find((r) => r.id === f.properties.route)
      const cp = route?.checkpoints[f.properties.index]
      if (!route || !cp) return
      e.originalEvent.stopPropagation()
      latest.current.onSelectRoute(route.id)
      popupRef.current?.remove()
      popupRef.current = new maplibregl.Popup({ maxWidth: '280px' })
        .setLngLat([cp.lon, cp.lat])
        .setHTML(checkpointPopupHtml(route.name, cp))
        .addTo(map)
    })
    for (const layer of ['routes', 'checkpoints']) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
    }

    // Heatmap hover readout, throttled to one update per animation frame.
    hoverPopupRef.current = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'hover-popup', offset: 12 })
    let pending = false
    map.on('mousemove', (e) => {
      if (pending) return
      pending = true
      requestAnimationFrame(() => {
        pending = false
        const { plan: p, heatmap: hm, frames: fr, hour: h, showHeatmap: show } = latest.current
        const hover = hoverPopupRef.current!
        const overFeature = map.queryRenderedFeatures(e.point, { layers: ['checkpoints', 'routes'] }).length > 0
        const idx = p && hm && fr && show && !overFeature ? cellAt(p.heatmap_grid, fr, e.lngLat.lng, e.lngLat.lat) : -1
        if (idx < 0 || !hm) {
          hover.remove()
          return
        }
        const score = hm.scores[h][idx]
        hover
          .setLngLat(e.lngLat)
          .setHTML(
            `<b>${RISK_LABELS[Math.floor(score)]}</b> · wind ${hm.wind_mph[h][idx]} mph · rain ${hm.rain_in_hr[h][idx].toFixed(2)}″/h · snow ${hm.snow_in_hr[h][idx].toFixed(2)}″/h`,
          )
          .addTo(map)
      })
    })
    map.on('mouseout', () => hoverPopupRef.current?.remove())

    return () => map.remove()
  }, [])

  // --- Route + checkpoint data ---
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    let cancelled = false
    readyRef.current!.then(() => {
      if (cancelled) return
      const routes = plan?.routes ?? []
      const routeFc: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: routes.map((r) => ({
          type: 'Feature',
          properties: { id: r.id, color: ROUTE_COLORS[r.id] ?? '#334155', selected: r.id === selectedRoute },
          geometry: { type: 'LineString', coordinates: r.geometry.map(([lat, lon]) => [lon, lat]) },
        })),
      }
      const cpFc: GeoJSON.FeatureCollection = {
        type: 'FeatureCollection',
        features: routes.flatMap((r) =>
          r.checkpoints.map((cp) => ({
            type: 'Feature' as const,
            properties: {
              route: r.id,
              index: cp.index,
              level: cp.risk.level,
              color: RISK_COLORS[cp.risk.level],
              selected: r.id === selectedRoute,
            },
            geometry: { type: 'Point' as const, coordinates: [cp.lon, cp.lat] },
          })),
        ),
      }
      ;(map.getSource('routes') as GeoJSONSource).setData(routeFc)
      ;(map.getSource('checkpoints') as GeoJSONSource).setData(cpFc)
    })
    return () => {
      cancelled = true
    }
  }, [plan, selectedRoute])

  // --- Fit bounds + endpoint markers when a new plan arrives ---
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    endpointMarkers.current.forEach((m) => m.remove())
    endpointMarkers.current = []
    popupRef.current?.remove()
    if (!plan) return
    const bounds = new maplibregl.LngLatBounds()
    plan.routes.forEach((r) => r.geometry.forEach(([lat, lon]) => bounds.extend([lon, lat])))
    map.fitBounds(bounds, { padding: { top: 60, bottom: 150, left: 60, right: 60 }, duration: 800 })
    for (const [place, cls, label] of [
      [plan.origin, 'endpoint origin', 'Start'],
      [plan.destination, 'endpoint destination', 'End'],
    ] as const) {
      const el = document.createElement('div')
      el.className = cls
      el.textContent = label
      el.title = `${label}: ${place.name}`
      endpointMarkers.current.push(new maplibregl.Marker({ element: el }).setLngLat([place.lon, place.lat]).addTo(map))
    }
  }, [plan])

  // --- Heatmap frames + slider ---
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    let cancelled = false
    readyRef.current!.then(() => {
      if (cancelled) return
      const visible = showHeatmap && frames
      map.setLayoutProperty('heatmap', 'visibility', visible ? 'visible' : 'none')
      if (visible) {
        ;(map.getSource('heatmap') as ImageSource).updateImage({
          url: frames.urls[Math.min(hour, frames.urls.length - 1)],
          coordinates: frames.coordinates,
        })
      } else {
        hoverPopupRef.current?.remove()
      }
    })
    return () => {
      cancelled = true
    }
  }, [frames, hour, showHeatmap])

  // --- Truck marker for the selected route at the slider time ---
  const track = useMemo(() => {
    const r = plan?.routes.find((x) => x.id === selectedRoute)
    return r ? makeTrack(r) : null
  }, [plan, selectedRoute])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !track || !plan) {
      truckRef.current?.remove()
      truckRef.current = null
      return
    }
    const sliderStart = heatmap ? new Date(heatmap.start).getTime() : new Date(plan.departure).getTime()
    const hoursSinceDeparture = (sliderStart + hour * 3600_000 - new Date(plan.departure).getTime()) / 3600_000
    const { lngLat, state } = positionAt(track, hoursSinceDeparture)
    if (!truckRef.current) {
      const el = document.createElement('div')
      el.className = 'truck-marker'
      el.textContent = '🚚'
      truckRef.current = new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map)
    }
    truckRef.current.setLngLat(lngLat)
    const el = truckRef.current.getElement()
    el.classList.toggle('idle', state !== 'en-route')
    el.title = state === 'not-departed' ? 'Not departed yet' : state === 'arrived' ? 'Arrived' : 'Estimated truck position'
  }, [track, plan, heatmap, hour])

  // --- Fly to a checkpoint picked from the table ---
  useEffect(() => {
    const map = mapRef.current
    if (!map || !focus || !plan) return
    const route = plan.routes.find((r) => r.checkpoints.includes(focus))
    map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 7), duration: 700 })
    popupRef.current?.remove()
    popupRef.current = new maplibregl.Popup({ maxWidth: '280px' })
      .setLngLat([focus.lon, focus.lat])
      .setHTML(checkpointPopupHtml(route?.name ?? '', focus))
      .addTo(map)
  }, [focus, plan])

  return <div ref={containerRef} className="map" />
}
