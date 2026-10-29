"""Orchestrates a trip plan: routes -> checkpoints with ETAs -> weather -> risk -> ranking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import geo, ranking, routing, weather
from .geocoding import Place
from .risk import assess, risk_score

ROUTE_NAMES = ("Route A", "Route B", "Route C")
HEATMAP_HOURS = 48


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime
    load_lb: float
    interval_miles: float


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def plan_trip(req: TripRequest) -> dict:
    routes = routing.find_routes((req.origin.lat, req.origin.lon), (req.destination.lat, req.destination.lon))

    # Gather every checkpoint across all routes so weather is fetched in one batch.
    samples = [routing.sample_every(r, req.interval_miles) for r in routes]
    flat = [p for route_samples in samples for p in route_samples]
    longest_h = max(r.duration_hours for r in routes)
    forecasts = weather.forecasts([(p.lat, p.lon) for p in flat], req.departure, math.ceil(longest_h) + 2)

    built = []
    cursor = 0
    for name, route, points in zip(ROUTE_NAMES, routes, samples):
        checkpoints = []
        levels = []
        for i, p in enumerate(points):
            eta = req.departure + timedelta(hours=p.hours)
            cond = forecasts[cursor].at(eta)
            cursor += 1
            a = assess(cond.wind_mph, cond.rain_in_hr, cond.snow_in_hr, req.load_lb)
            levels.append(a.level)
            checkpoints.append({
                "index": i,
                "mile": round(p.mile, 1),
                "lat": round(p.lat, 5),
                "lon": round(p.lon, 5),
                "eta": _iso(eta),
                "hours_from_departure": round(p.hours, 3),
                "weather": cond.as_dict(),
                "risk": a.as_dict(),
            })
        summary = ranking.summarize([c["mile"] for c in checkpoints], levels, route.distance_miles)
        built.append({
            "name": name,
            "route": route,
            "summary": summary,
            "checkpoints": checkpoints,
        })

    order = sorted(built, key=lambda b: ranking.sort_key(b["summary"], b["route"].duration_hours))
    for rank, b in enumerate(order, start=1):
        b["rank"] = rank

    best = order[0]
    if len(order) > 1:
        runner = order[1]
        reason = ranking.explain(
            best["summary"], best["route"].duration_hours,
            runner["summary"], runner["route"].duration_hours, runner["name"],
        )
    else:
        reason = "Only one distinct route was found between these locations."

    return {
        "origin": req.origin.as_dict(),
        "destination": req.destination.as_dict(),
        "departure": _iso(req.departure),
        "load_lb": req.load_lb,
        "interval_miles": req.interval_miles,
        "recommended": best["name"],
        "recommendation_reason": reason,
        "routes": [
            {
                "id": b["name"],
                "name": b["name"],
                "rank": b["rank"],
                "via": b["route"].summary,
                "distance_miles": round(b["route"].distance_miles, 1),
                "duration_hours": round(b["route"].duration_hours, 3),
                "arrival": _iso(req.departure + timedelta(hours=b["route"].duration_hours)),
                "risk": b["summary"].as_dict(),
                "geometry": [[round(lat, 5), round(lon, 5)] for lat, lon in geo.simplify(b["route"].coords)],
                "checkpoints": b["checkpoints"],
            }
            for b in built
        ],
        "heatmap_grid": routing.corridor_grid(routes),
    }


def heatmap(cells: list[tuple[float, float]], start: datetime, load_lb: float) -> dict:
    """Risk score per cell for each hour 0..48 after `start`.

    Returned column-major by hour (`scores[h][cell]`) so the UI can swap a whole frame at once.
    """
    start = weather.floor_hour(start)
    fcs = weather.forecasts(cells, start, HEATMAP_HOURS)
    scores, wind, rain, snow = [], [], [], []
    for h in range(HEATMAP_HOURS + 1):
        conds = [fc.at_hour(h) for fc in fcs]
        scores.append([round(risk_score(c.wind_mph, c.rain_in_hr, c.snow_in_hr, load_lb), 2) for c in conds])
        wind.append([round(c.wind_mph) for c in conds])
        rain.append([round(c.rain_in_hr, 2) for c in conds])
        snow.append([round(c.snow_in_hr, 2) for c in conds])
    return {
        "start": _iso(start),
        "hours": HEATMAP_HOURS,
        "cells": [[lat, lon] for lat, lon in cells],
        "scores": scores,
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
    }
