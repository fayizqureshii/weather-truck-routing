"""Weather risk classification, implementing the assessment's risk and load rules.

Levels are ordered integers so they can be compared, averaged and maxed:
    0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel

Boundary handling (the spec's ranges share endpoints, so we pin them down):
    Wind (mph):   <25 Low | 25–<35 Moderate | 35–<45 High | 45–<55 Severe | >=55 No Travel
    Rain (in/hr): <0.10 Low | 0.10–<0.25 Moderate | 0.25–<0.50 High | 0.50–1.00 Severe | >1.00 No Travel
    Snow (in/hr): <0.5 Low  | 0.5–<1.0 Moderate   | 1.0–<2.0 High   | 2.0–3.0 Severe   | >3.0 No Travel

A value sitting exactly on a shared endpoint goes to the higher class (e.g. 0.25 in/hr
rain is High), except the top endpoints of Severe for rain/snow, where the spec says
No Travel only starts strictly above 1.00 / 3.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return RISK_LABELS[self]


RISK_LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}

HEAVY_LOAD_SEVERE_LB = 40_000  # 35–44 mph wind + load above this -> Severe
HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # 45–54 mph wind + load above this -> No Travel


def classify_wind(mph: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(in_per_hr: float) -> Risk:
    if in_per_hr > 1.00:
        return Risk.NO_TRAVEL
    if in_per_hr >= 0.50:
        return Risk.SEVERE
    if in_per_hr >= 0.25:
        return Risk.HIGH
    if in_per_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(in_per_hr: float) -> Risk:
    if in_per_hr > 3.0:
        return Risk.NO_TRAVEL
    if in_per_hr >= 2.0:
        return Risk.SEVERE
    if in_per_hr >= 1.0:
        return Risk.HIGH
    if in_per_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def apply_load_rules(wind_mph: float, wind_risk: Risk, load_lb: float) -> Risk:
    """Escalate wind risk for heavy loads. Never lowers a level."""
    if wind_mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= wind_mph < 55 and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return Risk.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lb > HEAVY_LOAD_SEVERE_LB:
        return max(wind_risk, Risk.SEVERE)
    return wind_risk


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "level": int(self.level),
            "label": self.level.label,
            "components": {
                "wind": int(self.wind),
                "rain": int(self.rain),
                "snow": int(self.snow),
            },
            "reasons": self.reasons,
        }


_SCORE_EDGES = {
    "wind": (0, 25, 35, 45, 55),
    "rain": (0, 0.10, 0.25, 0.50, 1.00),
    "snow": (0, 0.5, 1.0, 2.0, 3.0),
}


def _band_score(value: float, edges: tuple[float, ...]) -> float:
    """Piecewise-linear 0–4 score: the band index plus how far through the band the value is."""
    for i in range(len(edges) - 1):
        if value < edges[i + 1]:
            return i + (value - edges[i]) / (edges[i + 1] - edges[i])
    return 4.0


def risk_score(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> float:
    """Continuous 0–4 score used to shade the heatmap smoothly.

    Always consistent with `assess`: floor(score) == assess(...).level.
    """
    level = assess(wind_mph, rain_in_hr, snow_in_hr, load_lb).level
    raw = max(
        _band_score(wind_mph, _SCORE_EDGES["wind"]),
        _band_score(rain_in_hr, _SCORE_EDGES["rain"]),
        _band_score(snow_in_hr, _SCORE_EDGES["snow"]),
    )
    return min(max(raw, float(level)), level + 0.99)


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk at a point is the worst of its wind (load-adjusted), rain and snow risk."""
    base_wind = classify_wind(wind_mph)
    wind = apply_load_rules(wind_mph, base_wind, load_lb)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    level = max(wind, rain, snow)

    reasons: list[str] = []
    if wind > Risk.LOW:
        text = f"Wind {wind_mph:.0f} mph ({wind.label})"
        if wind > base_wind:
            text += f" — escalated from {base_wind.label} for a {load_lb:,.0f} lb load"
        reasons.append(text)
    if rain > Risk.LOW:
        reasons.append(f"Rain {rain_in_hr:.2f} in/hr ({rain.label})")
    if snow > Risk.LOW:
        reasons.append(f"Snow {snow_in_hr:.2f} in/hr ({snow.label})")

    return Assessment(level=level, wind=wind, rain=rain, snow=snow, reasons=reasons)
