"""Hourly forecasts from Open-Meteo (free, no key), fetched for many points per request.

Open-Meteo hourly precipitation values (rain, snowfall) are totals for the hour *ending*
at the timestamp, so a rate in in/hr. Wind is an instantaneous value at the timestamp.
"""

from __future__ import annotations

import hashlib
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.cache import cache

from .geo import LatLon
from .http import UpstreamError, get_json

HOURLY_VARS = ("wind_speed_10m", "wind_gusts_10m", "rain", "snowfall", "temperature_2m", "weather_code")
POINTS_PER_REQUEST = 50
MAX_FORECAST_DAYS = 16


@dataclass(frozen=True)
class Conditions:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temp_f: float
    weather_code: int

    def as_dict(self) -> dict:
        return {
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 2),
            "temp_f": round(self.temp_f, 1),
            "weather_code": self.weather_code,
        }


class Forecast:
    """Hourly series for one location, starting at `start` (UTC, on the hour)."""

    def __init__(self, start: datetime, hourly: dict[str, list]):
        self.start = start
        self.hourly = hourly
        self.length = len(hourly["wind_speed_10m"])

    def _value(self, var: str, index: int) -> float:
        index = min(max(index, 0), self.length - 1)
        v = self.hourly[var][index]
        return 0.0 if v is None else float(v)

    def at_hour(self, index: int) -> Conditions:
        return Conditions(
            wind_mph=self._value("wind_speed_10m", index),
            gust_mph=self._value("wind_gusts_10m", index),
            rain_in_hr=self._value("rain", index),
            snow_in_hr=self._value("snowfall", index),
            temp_f=self._value("temperature_2m", index),
            weather_code=int(self._value("weather_code", index)),
        )

    def at(self, when: datetime) -> Conditions:
        """Conditions when the truck passes: wind interpolated, precip from the hour in progress."""
        offset = (when - self.start).total_seconds() / 3600
        lo = math.floor(offset)
        frac = offset - lo
        hi = lo + 1 if frac > 0 else lo
        wind = self._value("wind_speed_10m", lo) * (1 - frac) + self._value("wind_speed_10m", hi) * frac
        gust = self._value("wind_gusts_10m", lo) * (1 - frac) + self._value("wind_gusts_10m", hi) * frac
        temp = self._value("temperature_2m", lo) * (1 - frac) + self._value("temperature_2m", hi) * frac
        # The precip bucket stamped `hi` covers (hi-1, hi], i.e. the hour the truck is in.
        return Conditions(
            wind_mph=wind,
            gust_mph=gust,
            rain_in_hr=self._value("rain", hi),
            snow_in_hr=self._value("snowfall", hi),
            temp_f=temp,
            weather_code=int(self._value("weather_code", hi)),
        )


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _fetch_chunk(points: list[LatLon], start: datetime, end: datetime) -> list[dict]:
    raw_key = "{}:{}:{}".format(
        start.strftime("%Y%m%d%H"),
        end.strftime("%Y%m%d%H"),
        ";".join(f"{lat:.2f},{lon:.2f}" for lat, lon in points),
    )
    key = "wx:" + hashlib.sha1(raw_key.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached

    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    data = get_json(f"{settings.OPEN_METEO_URL}/v1/forecast", params)
    results = data if isinstance(data, list) else [data]
    if len(results) != len(points) or any("hourly" not in r for r in results):
        raise UpstreamError("Weather service returned an unexpected response.")
    hourly = [r["hourly"] for r in results]
    cache.set(key, hourly, 60 * 15)
    return hourly


def forecasts(points: list[LatLon], start: datetime, hours: int) -> list[Forecast]:
    """One Forecast per point covering [start, start + hours], all on the same hourly grid."""
    start = floor_hour(start)
    end = start + timedelta(hours=hours)
    limit = floor_hour(datetime.now(timezone.utc)) + timedelta(days=MAX_FORECAST_DAYS) - timedelta(hours=1)
    if end > limit:
        raise ValueError("The trip extends beyond the 16-day weather forecast window.")

    # Routes share long stretches of road; points within ~0.5 mi share one forecast lookup.
    # (Open-Meteo's free tier is rate limited per location, and its grid is ~1.5–11 km anyway.)
    unique: dict[LatLon, int] = {}
    for lat, lon in points:
        unique.setdefault((round(lat, 2), round(lon, 2)), len(unique))
    keys = list(unique)

    chunks = [keys[i : i + POINTS_PER_REQUEST] for i in range(0, len(keys), POINTS_PER_REQUEST)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: _fetch_chunk(c, start, end), chunks))
    by_key = [Forecast(start, hourly) for chunk in results for hourly in chunk]
    return [by_key[unique[(round(lat, 2), round(lon, 2))]] for lat, lon in points]
