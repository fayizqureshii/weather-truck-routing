import { formatDateTime } from '../format'
import { RISK_COLORS } from '../risk'
import type { Checkpoint, RouteOption } from '../types'

interface Props {
  route: RouteOption
  onFocus: (cp: Checkpoint) => void
}

export function CheckpointTable({ route, onFocus }: Props) {
  return (
    <div className="checkpoints">
      <h3>
        {route.name} checkpoints <span>({route.checkpoints.length})</span>
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mile</th>
              <th>ETA</th>
              <th>Risk</th>
              <th title="Sustained wind">Wind</th>
              <th title="Rain rate">Rain</th>
              <th title="Snowfall rate">Snow</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((cp) => (
              <tr key={cp.index} onClick={() => onFocus(cp)} title={cp.risk.reasons.join('\n') || 'No hazards'}>
                <td>{Math.round(cp.mile)}</td>
                <td>{formatDateTime(cp.eta)}</td>
                <td>
                  <span className="dot" style={{ background: RISK_COLORS[cp.risk.level] }} />
                  {cp.risk.label}
                </td>
                <td>{cp.weather.wind_mph.toFixed(0)}</td>
                <td>{cp.weather.rain_in_hr.toFixed(2)}</td>
                <td>{cp.weather.snow_in_hr.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="units">Wind mph · rain &amp; snow in/hr · click a row to locate it</p>
    </div>
  )
}
