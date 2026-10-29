import { useEffect, useId, useRef, useState } from 'react'
import { geocode } from '../api'
import type { Place } from '../types'

interface Props {
  label: string
  value: Place | string
  onChange: (value: Place | string) => void
  placeholder?: string
}

/** Free-text location field with debounced suggestions; picking one pins exact coordinates. */
export function LocationInput({ label, value, onChange, placeholder }: Props) {
  const id = useId()
  const text = typeof value === 'string' ? value : value.name
  const [suggestions, setSuggestions] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (typeof value !== 'string' || value.trim().length < 3) {
      setSuggestions([])
      return
    }
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      geocode(value, ctrl.signal)
        .then((r) => {
          setSuggestions(r.results)
          setActive(-1)
        })
        .catch(() => {})
    }, 250)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [value])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const pick = (p: Place) => {
    onChange(p)
    setOpen(false)
    setSuggestions([])
  }

  return (
    <div className="field location" ref={wrapRef}>
      <label htmlFor={id}>{label}</label>
      <div className="location-input">
        <input
          id={id}
          value={text}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls={`${id}-list`}
          onChange={(e) => {
            onChange(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (!open || suggestions.length === 0) return
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, suggestions.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter' && active >= 0) {
              e.preventDefault()
              pick(suggestions[active])
            } else if (e.key === 'Escape') {
              setOpen(false)
            }
          }}
        />
        {typeof value !== 'string' && <span className="pin" title="Exact location selected">📍</span>}
      </div>
      {open && suggestions.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.lat},${s.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(s)
              }}
            >
              {s.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
