import { useState, type FormEvent } from 'react'
import { toLocalInputValue } from '../format'
import type { Place, PlanInput } from '../types'
import { LocationInput } from './LocationInput'

interface Props {
  loading: boolean
  onSubmit: (input: PlanInput) => void
}

const INTERVALS = [10, 25, 50] as const

function nextHour(): Date {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}

export function PlanForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | string>('Chicago, IL')
  const [destination, setDestination] = useState<Place | string>('Denver, CO')
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextHour()))
  const [load, setLoad] = useState('42000')
  const [intervalMiles, setIntervalMiles] = useState<(typeof INTERVALS)[number]>(25)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_lb: Number(load),
      interval_miles: intervalMiles,
    })
  }

  return (
    <form className="plan-form" onSubmit={submit}>
      <LocationInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or address" />
      <button
        type="button"
        className="swap"
        title="Swap origin and destination"
        aria-label="Swap origin and destination"
        onClick={() => {
          setOrigin(destination)
          setDestination(origin)
        }}
      >
        ⇅
      </button>
      <LocationInput label="Destination" value={destination} onChange={setDestination} placeholder="City or address" />

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={toLocalInputValue(new Date())}
            onChange={(e) => setDeparture(e.target.value)}
            required
          />
        </div>
        <div className="field narrow">
          <label htmlFor="load">Load (lb)</label>
          <input
            id="load"
            type="number"
            min={0}
            max={80000}
            step={500}
            value={load}
            onChange={(e) => setLoad(e.target.value)}
            required
          />
        </div>
      </div>

      <div className="field">
        <span className="label">Weather checkpoint every</span>
        <div className="segmented" role="radiogroup" aria-label="Checkpoint interval">
          {INTERVALS.map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={intervalMiles === n}
              className={intervalMiles === n ? 'on' : ''}
              onClick={() => setIntervalMiles(n)}
            >
              {n} mi
            </button>
          ))}
        </div>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? 'Planning…' : 'Find safest route'}
      </button>
    </form>
  )
}
