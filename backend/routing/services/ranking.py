"""Route risk summaries and the recommendation order.

Spec order of preference:
    1. Fewest Severe miles  2. Fewest High miles  3. Lowest average risk  4. Shortest travel time

"No Travel" is strictly worse than Severe, so No Travel miles are compared before anything
else — a route that crosses a No Travel zone can never beat one that does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from .risk import RISK_LABELS, Risk

AVG_RISK_TOLERANCE = 0.05  # treat average-risk differences smaller than this as a tie


@dataclass(frozen=True)
class RiskSummary:
    miles_by_level: dict[Risk, float]
    average_risk: float
    max_level: Risk
    distance_miles: float

    def as_dict(self) -> dict:
        return {
            "miles_by_level": {RISK_LABELS[lvl]: round(m, 1) for lvl, m in self.miles_by_level.items()},
            "average_risk": round(self.average_risk, 3),
            "max_level": int(self.max_level),
            "max_label": self.max_level.label,
        }


def summarize(checkpoint_miles: list[float], levels: list[Risk], total_miles: float) -> RiskSummary:
    """Attribute each stretch of road to its nearest checkpoint.

    Checkpoint i covers from the midpoint with its previous checkpoint to the midpoint with
    its next one, so the miles always add up to the route length.
    """
    miles = {lvl: 0.0 for lvl in Risk}
    n = len(checkpoint_miles)
    for i, (mile, level) in enumerate(zip(checkpoint_miles, levels)):
        start = 0.0 if i == 0 else (checkpoint_miles[i - 1] + mile) / 2
        end = total_miles if i == n - 1 else (mile + checkpoint_miles[i + 1]) / 2
        miles[level] += max(end - start, 0.0)
    weighted = sum(int(lvl) * m for lvl, m in miles.items())
    return RiskSummary(
        miles_by_level=miles,
        average_risk=weighted / total_miles if total_miles else 0.0,
        max_level=max(levels) if levels else Risk.LOW,
        distance_miles=total_miles,
    )


def sort_key(summary: RiskSummary, duration_hours: float) -> tuple:
    m = summary.miles_by_level
    return (
        round(m[Risk.NO_TRAVEL], 1),
        round(m[Risk.SEVERE], 1),
        round(m[Risk.HIGH], 1),
        round(summary.average_risk / AVG_RISK_TOLERANCE),
        duration_hours,
    )


def explain(winner: RiskSummary, winner_hours: float,
            runner: RiskSummary, runner_hours: float, runner_name: str) -> str:
    """One sentence naming the first criterion that separated the top two routes."""
    wk, rk = sort_key(winner, winner_hours), sort_key(runner, runner_hours)
    for idx, level, label in ((0, Risk.NO_TRAVEL, "No Travel"), (1, Risk.SEVERE, "Severe"), (2, Risk.HIGH, "High")):
        if wk[idx] != rk[idx]:
            a, b = winner.miles_by_level[level], runner.miles_by_level[level]
            return f"Fewer {label} miles than {runner_name} ({a:.0f} vs {b:.0f} mi)."
    if wk[3] != rk[3]:
        return (
            f"Same Severe/High exposure as {runner_name}, lower average risk "
            f"({winner.average_risk:.2f} vs {runner.average_risk:.2f})."
        )
    if wk[4] != rk[4]:
        return (
            f"Weather risk equivalent to {runner_name}, and faster "
            f"({winner_hours:.1f} h vs {runner_hours:.1f} h)."
        )
    return f"Identical risk and travel time to {runner_name}."
