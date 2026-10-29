import { formatDateTime, formatDuration, formatMiles } from '../format'
import { RISK_COLORS, RISK_LABELS, ROUTE_COLORS } from '../risk'
import type { Plan, RiskLevel } from '../types'

interface Props {
  plan: Plan
  selected: string | null
  onSelect: (id: string) => void
}

function RiskBar({ milesByLevel, total }: { milesByLevel: Record<string, number>; total: number }) {
  return (
    <div className="risk-bar" aria-label="Miles by risk level">
      {RISK_LABELS.map((label, lvl) => {
        const miles = milesByLevel[label] ?? 0
        if (miles <= 0) return null
        return (
          <span
            key={label}
            style={{ width: `${(miles / total) * 100}%`, background: RISK_COLORS[lvl as RiskLevel] }}
            title={`${label}: ${Math.round(miles)} mi`}
          />
        )
      })}
    </div>
  )
}

export function RouteCards({ plan, selected, onSelect }: Props) {
  const ordered = [...plan.routes].sort((a, b) => a.rank - b.rank)
  return (
    <div className="route-cards">
      {ordered.map((r) => {
        const m = r.risk.miles_by_level
        const recommended = r.id === plan.recommended
        return (
          <button
            key={r.id}
            type="button"
            className={`route-card ${selected === r.id ? 'selected' : ''}`}
            onClick={() => onSelect(r.id)}
            style={{ borderLeftColor: ROUTE_COLORS[r.id] }}
          >
            <div className="route-card-head">
              <span className="route-name">
                <i style={{ background: ROUTE_COLORS[r.id] }} />
                {r.name}
              </span>
              {recommended ? <span className="badge">Recommended</span> : <span className="rank">#{r.rank}</span>}
            </div>
            {r.via && <div className="via">via {r.via}</div>}
            <div className="stats">
              <div>
                <b>{formatMiles(r.distance_miles)}</b>
                <span>distance</span>
              </div>
              <div>
                <b>{formatDuration(r.duration_hours)}</b>
                <span>drive time</span>
              </div>
              <div>
                <b>{formatDateTime(r.arrival)}</b>
                <span>arrival</span>
              </div>
            </div>
            <RiskBar milesByLevel={m} total={r.distance_miles} />
            <div className="risk-line">
              <span className="pill" style={{ background: RISK_COLORS[r.risk.max_level] }}>
                Worst: {r.risk.max_label}
              </span>
              <span>Severe {Math.round(m['Severe'] + m['No Travel'])} mi</span>
              <span>High {Math.round(m['High'])} mi</span>
              <span>Avg {r.risk.average_risk.toFixed(2)}</span>
            </div>
            {m['No Travel'] > 0 && (
              <div className="warning">⚠ Crosses {Math.round(m['No Travel'])} mi of No Travel conditions</div>
            )}
          </button>
        )
      })}
    </div>
  )
}
