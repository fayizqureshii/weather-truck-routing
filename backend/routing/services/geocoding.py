"""Geocoding via Photon (OpenStreetMap data, free, no key)."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

from .http import get_json


class LocationNotFound(ValueError):
    pass


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {"name": self.name, "lat": self.lat, "lon": self.lon}


def _label(props: dict) -> str:
    parts = [props.get("name")]
    for key in ("city", "state", "country"):
        value = props.get(key)
        if value and value not in parts:
            parts.append(value)
    return ", ".join(p for p in parts if p)


def search(query: str, limit: int = 5) -> list[Place]:
    query = query.strip()
    if not query:
        return []
    cache_key = f"geocode:{limit}:{query.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = get_json(f"{settings.PHOTON_URL}/api/", {"q": query, "limit": limit, "lang": "en"})
    places = []
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"]
        places.append(Place(name=_label(feature.get("properties", {})), lat=lat, lon=lon))
    cache.set(cache_key, places, 60 * 60 * 24)
    return places


def resolve(query_or_coords: str | dict) -> Place:
    """Accept either free text or an already-resolved {name, lat, lon} from the UI."""
    if isinstance(query_or_coords, dict):
        return Place(
            name=query_or_coords.get("name") or "Selected location",
            lat=float(query_or_coords["lat"]),
            lon=float(query_or_coords["lon"]),
        )
    results = search(query_or_coords, limit=1)
    if not results:
        raise LocationNotFound(f"Could not find a location matching “{query_or_coords}”.")
    return results[0]
