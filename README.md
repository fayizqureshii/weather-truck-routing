# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route between two places, using
forecast weather **at the time the truck will actually reach each point**, the truck's load weight,
and travel time.

- 3 route options per trip (OSRM), drawn on a MapLibre map
- Weather checkpoints every **10 / 25 / 50 miles**, each with its own ETA and forecast (Open-Meteo)
- Risk per checkpoint from the spec's wind / rain / snow thresholds **plus the load rules**
- A recommendation that follows the spec's order of preference, with a one-line explanation of why
- A weather-risk **heatmap along the trip corridor** with a **0–48 h forecast slider** (and play button);
  a 🚚 marker shows where the truck would be at the selected hour

No API keys are needed: routing, geocoding and weather all use free public services.

---

## Running locally

Requirements: Python 3.12+, Node 20+.

```bash
# API (http://127.0.0.1:8000)
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py runserver
```

```bash
# UI with hot reload (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Or build the UI once and let Django serve everything on :8000:

```bash
cd frontend && npm run build
```

Tests (risk thresholds, load rules, ranking order, checkpoint sampling, ETA/forecast lookup):

```bash
cd backend && .venv/bin/python manage.py test routing
```

## Deploying

The repo has a multi-stage `Dockerfile`: it builds the React app, then runs Django with gunicorn
and serves the built files with WhiteNoise, so the whole app is one web service.

**Render:** New → Blueprint → select this repo. `render.yaml` sets everything up (free plan,
health check at `/api/health`). Any Docker host works the same way; set these environment variables:

| Variable | Example | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | long random string | required in production |
| `DJANGO_DEBUG` | `false` | the Dockerfile already sets this |
| `DJANGO_ALLOWED_HOSTS` | `myapp.onrender.com` | comma-separated |
| `OPEN_METEO_URL`, `OPEN_METEO_API_KEY` | `https://customer-api.open-meteo.com`, key | optional, to avoid free-tier rate limits |
| `TRUCK_MAX_SPEED_MPH` | `65` | truck speed cap (see below) |

---

## How it works

```
Browser (React + MapLibre)
  │  POST /api/plan     {origin, destination, departure, load_lb, interval_miles}
  │  POST /api/heatmap  {cells, start, load_lb}      ← called right after, in the background
  │  GET  /api/geocode?q=                            ← location autocomplete
  ▼
Django REST Framework  (backend/routing)
  ├─ geocoding.py   Photon (OpenStreetMap) search
  ├─ routing.py     OSRM routes, alternative generation, checkpoint sampling, heatmap grid
  ├─ weather.py     Open-Meteo hourly forecasts, batched, cached 15 min
  ├─ risk.py        threshold + load rules (pure functions)
  ├─ ranking.py     miles per risk level, recommendation order, explanation
  └─ planner.py     ties it together into the response
```

### 1. Routes

OSRM's `alternatives=3` often returns only 1–2 routes. When that happens the backend asks for
more by routing through **via points offset to either side of the fastest route** (at 35 %, 50 % and
65 % of the way). Candidates are kept only if they are:

- **distinct**: two routes count as the same if each one mostly (≥ 85 %) runs along the other,
  compared on a coarse grid of points sampled every 2 miles
- **reasonable**: no more than 1.6× the fastest drive time

**Truck travel time.** The public OSRM server only has a car profile, so each road segment's speed
is capped at `TRUCK_MAX_SPEED_MPH` (65 mph). ETAs come from OSRM's **per-segment** durations, so a
slow city stretch and a fast interstate get different speeds; they are not a single average spread
over the whole route.

### 2. Checkpoints and ETAs

Along each route's full-resolution geometry the backend places a checkpoint at mile 0, every
*N* miles (10, 25 or 50), and at the destination. Each checkpoint's ETA is
`departure + cumulative segment time up to that point`, interpolated inside the segment.

### 3. Weather at the ETA

All checkpoints across all three routes are fetched in batched Open-Meteo requests (50 locations
per request, in parallel). Points within ~0.5 mi of each other share one lookup, since the three
routes overlap a lot. Values are read at the truck's ETA:

- **Wind** (sustained 10 m wind, mph) is interpolated linearly between the two surrounding hours.
- **Rain / snowfall** (in/hr) come from the hourly bucket **the truck is driving through**.
  Open-Meteo stamps each precipitation value at the *end* of its hour, so an ETA of 14:20 uses
  the 15:00 value, which covers 14:00–15:00.

### 4. Risk rules

Levels: `0 Low · 1 Moderate · 2 High · 3 Severe · 4 No Travel`. A checkpoint's level is the worst of its
wind, rain and snow levels.

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | < 25 | 25 – < 35 | 35 – < 45 | 45 – < 55 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10 – < 0.25 | 0.25 – < 0.50 | 0.50 – 1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5 – < 1.0 | 1.0 – < 2.0 | 2.0 – 3.0 | > 3.0 |

The spec's ranges share their endpoints (e.g. rain "0.10–0.25" and "0.25–0.50"), so I had to pick
which side each endpoint falls on: a value exactly on a shared boundary goes to the **higher**
level, and No Travel for rain and snow starts *strictly above* 1.00 and 3.0, as the spec says.

**Load rules** (applied to wind only, and they only ever raise a level):

- ≥ 55 mph → No Travel for any load
- 45–54 mph and load > 30,000 lb → No Travel
- 35–44 mph and load > 40,000 lb → Severe

When a load rule raises a level, the checkpoint says so (e.g. *"Wind 40 mph (Severe), escalated
from High for a 45,000 lb load"*).

### 5. Recommendation

Each stretch of road is assigned to its **nearest checkpoint**: checkpoint *i* covers from the
midpoint with the previous checkpoint to the midpoint with the next. That gives miles per risk level
that add up exactly to the route length, and a distance-weighted average risk.

Routes are sorted by:

0. **Fewest No Travel miles.** Not in the spec's list, but No Travel is worse than Severe, so a route
   through a No Travel zone should never win on a technicality.
1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk (differences under 0.05 count as a tie, so tiny forecast noise doesn't
   outweigh real time savings)
4. Shortest travel time

The UI names the criterion that separated the winner from the runner-up, e.g. *"Fewer Severe miles
than Route B (0 vs 50 mi)"* or *"Weather risk equivalent to Route B, and faster (17.8 h vs 19.9 h)"*.

### 6. Corridor heatmap and the 0–48 h slider

- The backend builds a grid of cells within **35 miles of any route**. The grid is regular in
  **Web Mercator**, the map's own projection. The spacing adapts to the trip length so a trip
  needs at most ~240 cells, which keeps it inside Open-Meteo's free-tier limits.
- `/api/heatmap` returns, for every cell and every hour 0–48 after departure, a continuous
  **risk score from 0 to 4**: the level plus how far the value is through that level's range. The
  score is built so that `floor(score) == risk level`, so the colours never disagree with the
  classification. Load rules apply here too.
- The browser pre-renders **all 49 hours** into tiny images, one pixel per cell, as soon as the data
  arrives. Moving the slider or pressing play only swaps an image on a MapLibre image layer, with
  no network call and no recomputation. Because the grid matches the map projection, pixels line
  up exactly, and the GPU's linear filtering blends neighbouring cells into a smooth field.
- Hovering the heatmap shows that cell's level, wind, rain and snow for the selected hour.

### Performance notes

- The plan response uses simplified geometry (Douglas–Peucker, ~40 m tolerance). A
  Chicago → Denver plan is about 90 KB.
- Routes appear first. The heatmap is fetched afterwards, so the map is usable while it loads.
- Weather and geocoding responses are cached in memory, and outbound requests retry with backoff
  on 429/5xx.
- MapLibre (WebGL) draws routes and checkpoints as GeoJSON layers, not DOM markers, so hundreds of
  checkpoints at 10-mile spacing stay smooth.

## Assumptions and limitations

- **Routing is a car profile with a speed cap.** It does not know about truck-restricted roads, low
  bridges or weight limits. A truck-aware engine (e.g. a self-hosted OSRM truck profile or
  GraphHopper truck) can be swapped in at `routing.py`, behind the same `Route` type.
- **No hours-of-service breaks.** ETAs assume continuous driving. Long trips would really include
  mandatory rest, which shifts later checkpoints to later forecast hours.
- **Wind** uses the sustained 10 m wind speed, as the thresholds read. Gusts are shown in checkpoint
  popups for context but are not scored.
- Free public services (OSRM demo server, Photon, Open-Meteo) have rate limits and no uptime
  guarantee. Their URLs are configurable via environment variables.
- Departure must be within 13 days, so every ETA falls inside Open-Meteo's 16-day forecast.

## Project layout

```
backend/
  config/            Django settings, URLs (API + SPA fallback)
  routing/
    services/        geo, geocoding, routing, weather, risk, ranking, planner
    tests/           unit tests for the rules and the maths
    serializers.py   request validation
    views.py         /api/plan, /api/heatmap, /api/geocode
frontend/
  src/
    components/      MapView, PlanForm, LocationInput, RouteCards, CheckpointTable, ForecastPanel
    heatmap.ts       pre-renders forecast hours to image frames
    position.ts      truck position at a given time along a route
    risk.ts          colours and score ramp
Dockerfile, render.yaml
```
