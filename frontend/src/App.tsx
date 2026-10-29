import { useCallback, useMemo, useRef, useState } from 'react'
import { fetchHeatmap, planTrip } from './api'
import { CheckpointTable } from './components/CheckpointTable'
import { ForecastPanel } from './components/ForecastPanel'
import { MapView } from './components/MapView'
import { PlanForm } from './components/PlanForm'
import { RouteCards } from './components/RouteCards'
import { buildFrames } from './heatmap'
import type { Checkpoint, Heatmap, Plan, PlanInput } from './types'

type HeatmapStatus = 'idle' | 'loading' | 'ready' | 'error'

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [focus, setFocus] = useState<Checkpoint | null>(null)

  const [heatmap, setHeatmap] = useState<Heatmap | null>(null)
  const [heatmapStatus, setHeatmapStatus] = useState<HeatmapStatus>('idle')
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  const submit = useCallback(async (input: PlanInput) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    setError(null)
    setPlaying(false)
    setHeatmap(null)
    setHeatmapStatus('idle')
    try {
      const result = await planTrip(input, ctrl.signal)
      setPlan(result)
      setSelected(result.recommended)
      setFocus(null)
      setHour(0)
      setLoading(false)

      // Routes are on screen; load the corridor heatmap in the background.
      setHeatmapStatus('loading')
      try {
        const hm = await fetchHeatmap(result.heatmap_grid, result.departure, result.load_lb, ctrl.signal)
        setHeatmap(hm)
        setHeatmapStatus('ready')
      } catch {
        if (!ctrl.signal.aborted) setHeatmapStatus('error')
      }
    } catch (e) {
      if (ctrl.signal.aborted) return
      setError(e instanceof Error ? e.message : 'Something went wrong.')
      setLoading(false)
    }
  }, [])

  const frames = useMemo(
    () => (plan && heatmap ? buildFrames(plan.heatmap_grid, heatmap) : null),
    [plan, heatmap],
  )
  const selectedRoute = plan?.routes.find((r) => r.id === selected) ?? null
  const recommended = plan?.routes.find((r) => r.id === plan.recommended)

  return (
    <div className="app">
      <aside className="sidebar">
        <header>
          <h1>
            <span aria-hidden>🚚</span> Weather-Aware Truck Routing
          </h1>
          <p>Compare three routes by forecast weather at the truck’s arrival time at each checkpoint.</p>
        </header>

        <PlanForm loading={loading} onSubmit={submit} />

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {loading && (
          <div className="loading">
            <span className="spinner" /> Finding routes and sampling the forecast…
          </div>
        )}

        {plan && !loading && recommended && (
          <>
            <div className="recommendation">
              <div className="rec-title">
                Take <b>{recommended.name}</b>
                {recommended.via && <> via {recommended.via}</>}
              </div>
              <div className="rec-reason">{plan.recommendation_reason}</div>
              <div className="rec-trip">
                {plan.origin.name} → {plan.destination.name} · {plan.load_lb.toLocaleString()} lb
              </div>
            </div>
            <RouteCards plan={plan} selected={selected} onSelect={setSelected} />
            {selectedRoute && <CheckpointTable route={selectedRoute} onFocus={setFocus} />}
          </>
        )}

        <footer>
          Routing: OSRM · Weather: Open-Meteo · Geocoding: Photon/OSM
        </footer>
      </aside>

      <main className="map-area">
        <MapView
          plan={plan}
          selectedRoute={selected}
          onSelectRoute={setSelected}
          heatmap={heatmap}
          frames={frames}
          hour={hour}
          showHeatmap={showHeatmap}
          focus={focus}
        />
        {plan && (
          <ForecastPanel
            start={heatmap?.start ?? null}
            hours={heatmap?.hours ?? 48}
            hour={hour}
            onHour={setHour}
            playing={playing}
            onPlaying={setPlaying}
            showHeatmap={showHeatmap}
            onShowHeatmap={setShowHeatmap}
            status={heatmapStatus}
          />
        )}
      </main>
    </div>
  )
}
