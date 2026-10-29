"""Route generation via OSRM, plus via-point alternatives when OSRM returns fewer than 3.

OSRM's public server only uses a car profile, so per-segment speeds are capped at
TRUCK_MAX_SPEED_MPH to approximate truck travel time.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from django.conf import settings

from . import geo
from .geo import LatLon
from .http import UpstreamError, get_json

TARGET_ROUTE_COUNT = 3
MAX_DETOUR_RATIO = 1.6  # reject alternatives slower than this multiple of the fastest
DUPLICATE_OVERLAP = 0.85  # routes sharing more than this fraction of their length are "the same"


class NoRouteFound(ValueError):
    pass


@dataclass
class Route:
    coords: list[LatLon]
    seg_miles: list[float]
    seg_hours: list[float]
    summary: str
    cum_miles: list[float] = field(init=False)
    cum_hours: list[float] = field(init=False)

    def __post_init__(self) -> None:
        self.cum_miles = [0.0]
        self.cum_hours = [0.0]
        for m, h in zip(self.seg_miles, self.seg_hours):
            self.cum_miles.append(self.cum_miles[-1] + m)
            self.cum_hours.append(self.cum_hours[-1] + h)

    @property
    def distance_miles(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_hours(self) -> float:
        return self.cum_hours[-1]


def _osrm(points: list[LatLon], alternatives: bool) -> list[dict]:
    coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "distance,duration",
        "steps": "true",  # needed for OSRM to fill in the leg "summary" (main road names)
        "alternatives": str(TARGET_ROUTE_COUNT) if alternatives else "false",
    }
    # OSRM answers "no route" with HTTP 400 and a JSON body describing why.
    data = get_json(f"{settings.OSRM_URL}/route/v1/driving/{coord_str}", params, ok_statuses=(400,))
    if data.get("code") != "Ok":
        if data.get("code") in {"NoRoute", "NoSegment"}:
            raise NoRouteFound("No drivable route connects those locations.")
        raise UpstreamError(f"Routing service error: {data.get('message') or data.get('code')}")
    return data["routes"]


def _parse(osrm_route: dict) -> Route:
    coords: list[LatLon] = [(lat, lon) for lon, lat in osrm_route["geometry"]["coordinates"]]
    durations: list[float] = []
    for leg in osrm_route["legs"]:
        durations.extend(leg["annotation"]["duration"])

    seg_miles = [geo.haversine_miles(a, b) for a, b in zip(coords, coords[1:])]
    if len(durations) != len(seg_miles):
        # Geometry and annotations disagree (can happen at via points): spread the total
        # duration over segments in proportion to their length.
        total_h = osrm_route["duration"] / 3600
        total_mi = sum(seg_miles) or 1.0
        seg_hours = [total_h * m / total_mi for m in seg_miles]
    else:
        seg_hours = [d / 3600 for d in durations]

    cap = settings.TRUCK_MAX_SPEED_MPH
    seg_hours = [max(h, m / cap) for m, h in zip(seg_miles, seg_hours)]

    names: list[str] = []
    for leg in osrm_route["legs"]:
        for name in re.split(r"[,;]\s*", leg.get("summary") or ""):
            if name and name not in names:
                names.append(name)
    return Route(coords=coords, seg_miles=seg_miles, seg_hours=seg_hours, summary=", ".join(names))


def _sample_keys(route: Route, step_miles: float, cell_deg: float) -> set[tuple[int, int]]:
    """Coarse grid cells a route passes through, used for overlap comparison."""
    keys = set()
    next_mark = 0.0
    for (lat, lon), d in zip(route.coords, route.cum_miles):
        if d >= next_mark:
            keys.add((math.floor(lat / cell_deg), math.floor(lon / cell_deg)))
            next_mark += step_miles
    return keys


def _overlap(a: Route, b: Route) -> float:
    """Fraction of route a's sampled cells that route b also passes through."""
    cell = 0.05  # ~3.5 miles
    ka = _sample_keys(a, 2.0, cell)
    kb = _sample_keys(b, 2.0, cell)
    # Allow a one-cell tolerance so parallel samples on the same road still match.
    kb_expanded = {(x + dx, y + dy) for x, y in kb for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    return len(ka & kb_expanded) / max(len(ka), 1)


def _is_distinct(candidate: Route, chosen: list[Route]) -> bool:
    # Two routes are duplicates only if each mostly lies on the other.
    return all(
        min(_overlap(candidate, r), _overlap(r, candidate)) < DUPLICATE_OVERLAP for r in chosen
    )


def _via_points(base: Route, origin: LatLon, dest: LatLon) -> list[LatLon]:
    """Points offset to either side of the fastest route, to coax out different corridors."""
    straight = geo.haversine_miles(origin, dest)
    offset = min(max(straight * 0.18, 8.0), 150.0)
    out = []
    for frac in (0.5, 0.35, 0.65):
        target = base.distance_miles * frac
        i = next(i for i, d in enumerate(base.cum_miles) if d >= target)
        anchor = base.coords[i]
        heading = geo.bearing_deg(base.coords[max(i - 5, 0)], base.coords[min(i + 5, len(base.coords) - 1)])
        for side in (90, -90):
            out.append(geo.offset_point(anchor, heading + side, offset))
    return out


def find_routes(origin: LatLon, dest: LatLon) -> list[Route]:
    """Return up to three distinct routes, fastest first."""
    primary = [_parse(r) for r in _osrm([origin, dest], alternatives=True)]
    if not primary:
        raise NoRouteFound("No drivable route connects those locations.")
    fastest = min(primary, key=lambda r: r.duration_hours)

    chosen: list[Route] = []
    for r in sorted(primary, key=lambda r: r.duration_hours):
        if r.duration_hours <= fastest.duration_hours * MAX_DETOUR_RATIO and (
            not chosen or _is_distinct(r, chosen)
        ):
            chosen.append(r)

    if len(chosen) < TARGET_ROUTE_COUNT:
        vias = _via_points(fastest, origin, dest)

        def fetch(via: LatLon) -> Route | None:
            try:
                return _parse(_osrm([origin, via, dest], alternatives=False)[0])
            except (UpstreamError, NoRouteFound, KeyError, IndexError):
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            candidates = [r for r in pool.map(fetch, vias) if r is not None]
        for r in sorted(candidates, key=lambda r: r.duration_hours):
            if len(chosen) >= TARGET_ROUTE_COUNT:
                break
            if r.duration_hours <= fastest.duration_hours * MAX_DETOUR_RATIO and _is_distinct(r, chosen):
                chosen.append(r)

    return chosen[:TARGET_ROUTE_COUNT]


@dataclass(frozen=True)
class RoutePoint:
    mile: float
    hours: float
    lat: float
    lon: float


def sample_every(route: Route, interval_miles: float) -> list[RoutePoint]:
    """Points every `interval_miles` along the route, always including origin and destination."""
    marks = []
    m = 0.0
    while m < route.distance_miles - 0.5:  # skip a mark that would sit right on the destination
        marks.append(m)
        m += interval_miles
    marks.append(route.distance_miles)

    out = []
    i = 0
    for mark in marks:
        while i < len(route.seg_miles) - 1 and route.cum_miles[i + 1] < mark:
            i += 1
        seg = route.seg_miles[i] if route.seg_miles else 0.0
        frac = 0.0 if seg == 0 else min(max((mark - route.cum_miles[i]) / seg, 0.0), 1.0)
        lat, lon = geo.interpolate(route.coords[i], route.coords[min(i + 1, len(route.coords) - 1)], frac)
        hours = route.cum_hours[i] + frac * (route.seg_hours[i] if route.seg_hours else 0.0)
        out.append(RoutePoint(mile=mark, hours=hours, lat=lat, lon=lon))
    return out


def _merc_y(lat: float) -> float:
    """Web Mercator y, expressed in 'degrees' so it shares units with longitude."""
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def _merc_lat(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(math.radians(y))) - math.pi / 2)


def corridor_grid(routes: list[Route], width_miles: float = 35.0, max_cells: int = 240) -> dict:
    """A raster of cells within `width_miles` of any route, for the weather heatmap.

    The grid is regular in Web Mercator (the map's projection), so the UI can paint one
    pixel per cell into an image and drape it over the map with exact alignment.
    """
    samples = [(p.lat, p.lon) for r in routes for p in sample_every(r, 5.0)]
    lats = [p[0] for p in samples]
    lons = [p[1] for p in samples]
    mid_lat = math.radians((min(lats) + max(lats)) / 2)
    pad_lat = width_miles / 69.0
    pad_lon = width_miles / (69.0 * max(math.cos(mid_lat), 0.2))
    west, east = min(lons) - pad_lon, max(lons) + pad_lon
    y_south, y_north = _merc_y(min(lats) - pad_lat), _merc_y(max(lats) + pad_lat)

    # Bucket samples so each candidate cell only checks nearby samples.
    bucket_deg = max(pad_lat, pad_lon)
    buckets: dict[tuple[int, int], list[LatLon]] = defaultdict(list)
    for p in samples:
        buckets[(math.floor(p[0] / bucket_deg), math.floor(p[1] / bucket_deg))].append(p)

    def near(p: LatLon) -> bool:
        bx, by = math.floor(p[0] / bucket_deg), math.floor(p[1] / bucket_deg)
        return any(
            geo.haversine_miles(p, s) <= width_miles
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for s in buckets.get((bx + dx, by + dy), ())
        )

    def build(spacing: float) -> tuple[int, int, list[list[float]]]:
        cols = max(math.ceil((east - west) / spacing), 1)
        rows = max(math.ceil((y_north - y_south) / spacing), 1)
        cells = []
        for row in range(rows):
            lat = _merc_lat(y_north - (row + 0.5) * spacing)
            for col in range(cols):
                lon = west + (col + 0.5) * spacing
                if near((lat, lon)):
                    cells.append([row, col, round(lat, 4), round(lon, 4)])
        return cols, rows, cells

    # Start from an area-based estimate, then widen the spacing until under budget.
    route_miles = sum(r.distance_miles for r in routes) / len(routes)
    deg_per_mile = 1 / (69.0 * max(math.cos(mid_lat), 0.2))
    spacing = max(0.1, math.sqrt(route_miles * 2 * width_miles * 1.5 / max_cells) * deg_per_mile)
    cols, rows, cells = build(spacing)
    while len(cells) > max_cells:
        spacing *= 1.12
        cols, rows, cells = build(spacing)

    return {
        "west": west,
        "east": west + cols * spacing,
        "north": _merc_lat(y_north),
        "south": _merc_lat(y_north - rows * spacing),
        "cols": cols,
        "rows": rows,
        "cells": cells,
    }
