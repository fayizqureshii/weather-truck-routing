"""Fallback forecasts from MET Norway's Locationforecast API (free, global, no key).

Used when Open-Meteo refuses us, which happens on hosts with shared outbound IPs
(e.g. free cloud tiers) where other tenants have used up Open-Meteo's per-IP quota.

The output mimics an Open-Meteo `hourly` block (same keys and units) so the rest of
the app doesn't care which provider answered. Differences, handled here:
  * one location per request (vs. many for Open-Meteo)
  * hourly steps for ~2.5 days, then 6-hourly; instant values are interpolated between steps
  * precipitation is a single liquid amount; it is counted as snow at or below 0 °C
    using the common 10:1 snow-to-liquid ratio
  * no gust value in the API, so gusts fall back to the sustained wind
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings

from .geo import LatLon
from .http import UpstreamError, get_json

MS_TO_MPH = 2.236936
MM_TO_IN = 1 / 25.4
SNOW_TO_LIQUID_RATIO = 10.0


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _interpolate(series: list[tuple[datetime, float]], t: datetime) -> float:
    if t <= series[0][0]:
        return series[0][1]
    for (t0, v0), (t1, v1) in zip(series, series[1:]):
        if t0 <= t <= t1:
            frac = (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * frac
    return series[-1][1]


def hourly(point: LatLon, start: datetime, end: datetime) -> dict[str, list]:
    lat, lon = point
    data = get_json(
        f"{settings.METNO_URL}/weatherapi/locationforecast/2.0/complete",
        {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"},
    )
    try:
        steps = [(_parse_time(s["time"]), s["data"]) for s in data["properties"]["timeseries"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("Fallback weather service returned an unexpected response.") from exc
    if not steps or steps[-1][0] < end:
        raise UpstreamError("Fallback weather forecast does not cover the whole trip.")

    wind = [(t, d["instant"]["details"].get("wind_speed", 0.0) * MS_TO_MPH) for t, d in steps]
    temp_c = [(t, d["instant"]["details"].get("air_temperature", 10.0)) for t, d in steps]

    # Liquid precipitation (mm) per clock hour, keyed by the hour's *end* like Open-Meteo.
    precip_mm: dict[datetime, float] = {}
    for t, d in steps:
        if "next_1_hours" in d:
            precip_mm.setdefault(t + timedelta(hours=1), d["next_1_hours"]["details"].get("precipitation_amount", 0.0))
        elif "next_6_hours" in d:
            per_hour = d["next_6_hours"]["details"].get("precipitation_amount", 0.0) / 6
            for h in range(1, 7):
                precip_mm.setdefault(t + timedelta(hours=h), per_hour)

    out: dict[str, list] = {k: [] for k in (
        "wind_speed_10m", "wind_gusts_10m", "rain", "snowfall", "temperature_2m", "weather_code")}
    t = start
    while t <= end:
        w = _interpolate(wind, t)
        c = _interpolate(temp_c, t)
        liquid_in = precip_mm.get(t, 0.0) * MM_TO_IN
        frozen = c <= 0.0
        out["wind_speed_10m"].append(w)
        out["wind_gusts_10m"].append(w)
        out["rain"].append(0.0 if frozen else liquid_in)
        out["snowfall"].append(liquid_in * SNOW_TO_LIQUID_RATIO if frozen else 0.0)
        out["temperature_2m"].append(c * 9 / 5 + 32)
        out["weather_code"].append(0)
        t += timedelta(hours=1)
    return out
