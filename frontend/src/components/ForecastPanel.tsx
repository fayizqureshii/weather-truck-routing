import { useEffect } from 'react'
import { formatDateTime } from '../format'
import { RISK_COLORS, RISK_LABELS } from '../risk'
import type { RiskLevel } from '../types'

interface Props {
  start: string | null
  hours: number
  hour: number
  onHour: (h: number) => void
  playing: boolean
  onPlaying: (p: boolean) => void
  showHeatmap: boolean
  onShowHeatmap: (s: boolean) => void
  status: 'idle' | 'loading' | 'ready' | 'error'
}

export function ForecastPanel(props: Props) {
  const { start, hours, hour, onHour, playing, onPlaying, showHeatmap, onShowHeatmap, status } = props

  useEffect(() => {
    if (!playing) return
    const t = window.setInterval(() => onHour((hour + 1) % (hours + 1)), 450)
    return () => window.clearInterval(t)
  }, [playing, hour, hours, onHour])

  const when = start ? new Date(new Date(start).getTime() + hour * 3600_000) : null
  const disabled = status !== 'ready'

  return (
    <div className="forecast-panel">
      <div className="forecast-top">
        <label className="toggle">
          <input type="checkbox" checked={showHeatmap} onChange={(e) => onShowHeatmap(e.target.checked)} />
          Weather heatmap
        </label>
        <span className="forecast-time">
          {status === 'loading' && 'Loading corridor forecast…'}
          {status === 'error' && 'Heatmap unavailable'}
          {status === 'ready' && when && (
            <>
              <b>+{hour} h</b> · {formatDateTime(when)}
            </>
          )}
        </span>
      </div>
      <div className="forecast-controls">
        <button
          type="button"
          className="play"
          disabled={disabled}
          onClick={() => onPlaying(!playing)}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min={0}
          max={hours}
          step={1}
          value={hour}
          disabled={disabled}
          onChange={(e) => onHour(Number(e.target.value))}
          aria-label="Forecast hour after departure"
        />
      </div>
      <div className="legend">
        {RISK_LABELS.map((label, lvl) => (
          <span key={label}>
            <i style={{ background: RISK_COLORS[lvl as RiskLevel] }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
