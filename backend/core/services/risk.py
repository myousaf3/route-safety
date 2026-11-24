"""Table-driven weather risk policy and route ranking.

The assessment thresholds are implemented as half-open bands. Boundary behaviour is
deliberately explicit and unit-tested:

Wind mph:   <25 Low | 25-34.99 Moderate | 35-44.99 High | 45-54.99 Severe | >=55 No Travel
Rain in/hr: <0.10 Low | 0.10-0.24 Moderate | 0.25-0.49 High | 0.50-1.00 Severe | >1.00 No Travel
Snow in/hr: <0.5 Low | 0.5-0.99 Moderate | 1.0-1.99 High | 2.0-3.00 Severe | >3.00 No Travel

Load overrides are applied after the base dimension risk:
  * wind >= 55 mph                      -> No Travel (already base policy)
  * 45 <= wind < 55 and weight > 30,000 -> No Travel
  * 35 <= wind < 45 and weight > 40,000 -> Severe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

RISK_POLICY_VERSION = "2026-11-a"


class RiskLevel(IntEnum):
    UNKNOWN = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5


RISK_LABELS = {
    RiskLevel.UNKNOWN: "Unknown",
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}

# Upper bound is exclusive unless noted in _band().
_WIND_BANDS: tuple[tuple[float, RiskLevel], ...] = (
    (25.0, RiskLevel.LOW),
    (35.0, RiskLevel.MODERATE),
    (45.0, RiskLevel.HIGH),
    (55.0, RiskLevel.SEVERE),
)
_RAIN_BANDS: tuple[tuple[float, RiskLevel], ...] = (
    (0.10, RiskLevel.LOW),
    (0.25, RiskLevel.MODERATE),
    (0.50, RiskLevel.HIGH),
)
_SNOW_BANDS: tuple[tuple[float, RiskLevel], ...] = (
    (0.5, RiskLevel.LOW),
    (1.0, RiskLevel.MODERATE),
    (2.0, RiskLevel.HIGH),
)

LOAD_NO_TRAVEL_WIND_FLOOR = 45.0
LOAD_NO_TRAVEL_WEIGHT = 30_000
LOAD_SEVERE_WIND_FLOOR = 35.0
LOAD_SEVERE_WEIGHT = 40_000


@dataclass(frozen=True)
class RiskReason:
    code: str
    dimension: str
    message: str
    risk: int


@dataclass
class RiskAssessment:
    base_risk: RiskLevel
    risk: RiskLevel
    reasons: list[RiskReason] = field(default_factory=list)
    unknown_dimensions: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return RISK_LABELS[self.risk]

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_risk": int(self.base_risk),
            "risk": int(self.risk),
            "risk_label": self.label,
            "reasons": [
                {
                    "code": reason.code,
                    "dimension": reason.dimension,
                    "message": reason.message,
                    "risk": reason.risk,
                }
                for reason in self.reasons
            ],
            "unknown_dimensions": self.unknown_dimensions,
        }


def _band(value: float, bands: tuple[tuple[float, RiskLevel], ...], top: RiskLevel) -> RiskLevel:
    for upper, level in bands:
        if value < upper:
            return level
    return top


def classify_wind(wind_mph: float) -> RiskLevel:
    if wind_mph >= 55.0:
        return RiskLevel.NO_TRAVEL
    return _band(wind_mph, _WIND_BANDS, RiskLevel.NO_TRAVEL)


def classify_rain(rain_in_hr: float) -> RiskLevel:
    if rain_in_hr < 0.10:
        return RiskLevel.LOW
    if rain_in_hr < 0.25:
        return RiskLevel.MODERATE
    if rain_in_hr < 0.50:
        return RiskLevel.HIGH
    if rain_in_hr <= 1.00:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def classify_snow(snow_in_hr: float) -> RiskLevel:
    if snow_in_hr < 0.5:
        return RiskLevel.LOW
    if snow_in_hr < 1.0:
        return RiskLevel.MODERATE
    if snow_in_hr < 2.0:
        return RiskLevel.HIGH
    if snow_in_hr <= 3.00:
        return RiskLevel.SEVERE
    return RiskLevel.NO_TRAVEL


def _fmt(value: float, unit: str, decimals: int = 1) -> str:
    return f"{value:.{decimals}f} {unit}"


def _dimension_reason(dimension: str, value: float, unit: str, level: RiskLevel) -> RiskReason:
    decimals = 2 if unit.endswith("/hr") else 0
    return RiskReason(
        code=f"{dimension}_{RISK_LABELS[level].lower().replace(' ', '_')}",
        dimension=dimension,
        message=f"{dimension.capitalize()} {_fmt(value, unit, decimals)} is "
        f"{RISK_LABELS[level].lower()}",
        risk=int(level),
    )


def assess_weather(
    *,
    wind_mph: float | None,
    rain_in_hr: float | None,
    snow_in_hr: float | None,
    load_weight_lb: int,
) -> RiskAssessment:
    """Classify one checkpoint and apply load-dependent overrides."""

    levels: list[RiskLevel] = []
    reasons: list[RiskReason] = []
    unknown: list[str] = []

    if wind_mph is None:
        unknown.append("wind")
    else:
        level = classify_wind(wind_mph)
        levels.append(level)
        if level > RiskLevel.LOW:
            reasons.append(_dimension_reason("wind", wind_mph, "mph", level))

    if rain_in_hr is None:
        unknown.append("rain")
    else:
        level = classify_rain(rain_in_hr)
        levels.append(level)
        if level > RiskLevel.LOW:
            reasons.append(_dimension_reason("rain", rain_in_hr, "in/hr", level))

    if snow_in_hr is None:
        unknown.append("snow")
    else:
        level = classify_snow(snow_in_hr)
        levels.append(level)
        if level > RiskLevel.LOW:
            reasons.append(_dimension_reason("snow", snow_in_hr, "in/hr", level))

    if not levels:
        return RiskAssessment(
            base_risk=RiskLevel.UNKNOWN,
            risk=RiskLevel.UNKNOWN,
            reasons=[
                RiskReason(
                    code="weather_unknown",
                    dimension="weather",
                    message="No forecast values available at this checkpoint",
                    risk=int(RiskLevel.UNKNOWN),
                )
            ],
            unknown_dimensions=unknown,
        )

    base_risk = max(levels)
    final_risk = base_risk

    if wind_mph is not None:
        if 45.0 <= wind_mph < 55.0 and load_weight_lb > LOAD_NO_TRAVEL_WEIGHT:
            final_risk = RiskLevel.NO_TRAVEL
            reasons.append(
                RiskReason(
                    code="load_wind_no_travel",
                    dimension="load",
                    message=(
                        f"Wind {wind_mph:.1f} mph with a {load_weight_lb:,} lb load exceeds the "
                        "30,000 lb no-travel limit"
                    ),
                    risk=int(RiskLevel.NO_TRAVEL),
                )
            )
        elif 35.0 <= wind_mph < 45.0 and load_weight_lb > LOAD_SEVERE_WEIGHT:
            if final_risk < RiskLevel.SEVERE:
                final_risk = RiskLevel.SEVERE
            reasons.append(
                RiskReason(
                    code="load_wind_severe",
                    dimension="load",
                    message=(
                        f"Wind {wind_mph:.1f} mph with a {load_weight_lb:,} lb load is rated "
                        "Severe for loads above 40,000 lb"
                    ),
                    risk=int(RiskLevel.SEVERE),
                )
            )

    # Deduplicate reason codes while preserving order.
    seen: set[str] = set()
    unique_reasons: list[RiskReason] = []
    for reason in reasons:
        if reason.code not in seen:
            seen.add(reason.code)
            unique_reasons.append(reason)

    return RiskAssessment(
        base_risk=base_risk,
        risk=final_risk,
        reasons=unique_reasons,
        unknown_dimensions=unknown,
    )


def aggregate_segment_metrics(
    *,
    cumulative_miles: list[float],
    risks: list[int],
    duration_seconds: float,
) -> dict[str, Any]:
    """Attribute each checkpoint's risk to surrounding road distance.

    Uses a midpoint rule: a checkpoint owns half of the segment before it and half of
    the segment after it. This avoids counting checkpoints instead of miles.
    """

    if len(cumulative_miles) != len(risks) or len(risks) < 2:
        return {
            "no_travel_miles": 0.0,
            "severe_miles": 0.0,
            "high_miles": 0.0,
            "average_risk_score": 0.0,
            "max_risk": 0,
            "risk_miles": {str(level): 0.0 for level in range(1, 6)},
        }

    risk_miles = {level: 0.0 for level in range(1, 6)}
    weighted_risk = 0.0
    known_miles = 0.0
    total = len(risks)

    for index, risk in enumerate(risks):
        if index == 0:
            weight = (cumulative_miles[1] - cumulative_miles[0]) / 2.0
        elif index == total - 1:
            weight = (cumulative_miles[-1] - cumulative_miles[-2]) / 2.0
        else:
            weight = (cumulative_miles[index + 1] - cumulative_miles[index - 1]) / 2.0
        weight = max(weight, 0.0)

        if 1 <= risk <= 5:
            risk_miles[risk] += weight
            weighted_risk += risk * weight
            known_miles += weight

    return {
        "no_travel_miles": round(risk_miles[5], 2),
        "severe_miles": round(risk_miles[4], 2),
        "high_miles": round(risk_miles[3], 2),
        "average_risk_score": round(weighted_risk / known_miles, 3) if known_miles else 0.0,
        "max_risk": max(risks),
        "risk_miles": {str(level): round(miles, 2) for level, miles in risk_miles.items()},
        "duration_seconds": round(duration_seconds, 1),
    }


def ranking_key(metrics: dict[str, Any]) -> tuple[float, float, float, float, float]:
    return (
        float(metrics.get("no_travel_miles", 0.0)),
        float(metrics.get("severe_miles", 0.0)),
        float(metrics.get("high_miles", 0.0)),
        float(metrics.get("average_risk_score", 0.0)),
        float(metrics.get("duration_seconds", 0.0)),
    )


def rank_routes(metrics_list: list[dict[str, Any]]) -> list[int]:
    """Return indices sorted by the required lexicographic recommendation key."""

    return sorted(range(len(metrics_list)), key=lambda i: ranking_key(metrics_list[i]))
