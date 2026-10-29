"""Small geometry helpers. Coordinates are (lat, lon) tuples in degrees."""

from __future__ import annotations

import math
from typing import Sequence

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344

LatLon = tuple[float, float]


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def interpolate(a: LatLon, b: LatLon, fraction: float) -> LatLon:
    """Linear interpolation; accurate enough for segments a few hundred metres long."""
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)


def offset_point(origin: LatLon, bearing_deg: float, distance_miles: float) -> LatLon:
    """Destination point given a start, bearing and great-circle distance."""
    lat1, lon1 = map(math.radians, origin)
    bearing = math.radians(bearing_deg)
    d = distance_miles / EARTH_RADIUS_MILES
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def cumulative_miles(coords: Sequence[LatLon]) -> list[float]:
    """Distance from the first coordinate to every coordinate along a polyline."""
    out = [0.0]
    for prev, cur in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_miles(prev, cur))
    return out


def simplify(coords: Sequence[LatLon], tolerance_deg: float = 0.0004) -> list[LatLon]:
    """Ramer–Douglas–Peucker simplification (iterative), for lighter map geometry."""
    n = len(coords)
    if n < 3:
        return list(coords)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    tol2 = tolerance_deg * tolerance_deg
    while stack:
        start, end = stack.pop()
        (ay, ax), (by, bx) = coords[start], coords[end]
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        worst, worst_i = -1.0, -1
        for i in range(start + 1, end):
            py, px = coords[i]
            if seg2 == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > worst:
                worst, worst_i = d2, i
        if worst > tol2:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))
    return [c for c, k in zip(coords, keep) if k]
