from __future__ import annotations

import pytest

from core.services.risk import (
    RiskLevel,
    aggregate_segment_metrics,
    assess_weather,
    classify_rain,
    classify_snow,
    classify_wind,
    rank_routes,
    ranking_key,
)


@pytest.mark.parametrize(
    ("wind", "expected"),
    [
        (0, RiskLevel.LOW),
        (24.99, RiskLevel.LOW),
        (25, RiskLevel.MODERATE),
        (34.99, RiskLevel.MODERATE),
        (35, RiskLevel.HIGH),
        (44.99, RiskLevel.HIGH),
        (45, RiskLevel.SEVERE),
        (54.99, RiskLevel.SEVERE),
        (55, RiskLevel.NO_TRAVEL),
        (80, RiskLevel.NO_TRAVEL),
    ],
)
def test_wind_boundaries(wind, expected):
    assert classify_wind(wind) == expected


@pytest.mark.parametrize(
    ("rain", "expected"),
    [
        (0.0, RiskLevel.LOW),
        (0.099, RiskLevel.LOW),
        (0.10, RiskLevel.MODERATE),
        (0.249, RiskLevel.MODERATE),
        (0.25, RiskLevel.HIGH),
        (0.499, RiskLevel.HIGH),
        (0.50, RiskLevel.SEVERE),
        (1.00, RiskLevel.SEVERE),
        (1.001, RiskLevel.NO_TRAVEL),
    ],
)
def test_rain_boundaries(rain, expected):
    assert classify_rain(rain) == expected


@pytest.mark.parametrize(
    ("snow", "expected"),
    [
        (0.0, RiskLevel.LOW),
        (0.499, RiskLevel.LOW),
        (0.50, RiskLevel.MODERATE),
        (0.999, RiskLevel.MODERATE),
        (1.0, RiskLevel.HIGH),
        (1.999, RiskLevel.HIGH),
        (2.0, RiskLevel.SEVERE),
        (3.00, RiskLevel.SEVERE),
        (3.001, RiskLevel.NO_TRAVEL),
    ],
)
def test_snow_boundaries(snow, expected):
    assert classify_snow(snow) == expected


def test_worst_dimension_wins():
    result = assess_weather(wind_mph=26, rain_in_hr=0.6, snow_in_hr=0.0, load_weight_lb=20_000)
    assert result.base_risk == RiskLevel.SEVERE
    assert result.risk == RiskLevel.SEVERE
    # Each non-low dimension contributes a reason; the worst dimension sets the risk.
    assert {reason.dimension for reason in result.reasons} == {"wind", "rain"}


@pytest.mark.parametrize(
    ("wind", "weight", "expected"),
    [
        (54.9, 1_000, RiskLevel.SEVERE),
        (45.0, 30_000, RiskLevel.SEVERE),
        (45.0, 30_001, RiskLevel.NO_TRAVEL),
        (54.99, 80_000, RiskLevel.NO_TRAVEL),
        (55.0, 1_000, RiskLevel.NO_TRAVEL),
        (40.0, 40_000, RiskLevel.HIGH),
        (40.0, 40_001, RiskLevel.SEVERE),
        (35.0, 40_001, RiskLevel.SEVERE),
        (34.99, 80_000, RiskLevel.MODERATE),
    ],
)
def test_load_overrides(wind, weight, expected):
    result = assess_weather(wind_mph=wind, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=weight)
    assert result.risk == expected


def test_load_override_adds_reason_codes():
    no_travel = assess_weather(wind_mph=48, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=35_000)
    assert no_travel.risk == RiskLevel.NO_TRAVEL
    assert any(reason.code == "load_wind_no_travel" for reason in no_travel.reasons)

    severe = assess_weather(wind_mph=38, rain_in_hr=0.0, snow_in_hr=0.0, load_weight_lb=45_000)
    assert severe.risk == RiskLevel.SEVERE
    assert any(reason.code == "load_wind_severe" for reason in severe.reasons)


def test_missing_weather_is_unknown_not_safe():
    result = assess_weather(wind_mph=None, rain_in_hr=None, snow_in_hr=None, load_weight_lb=42_000)
    assert result.risk == RiskLevel.UNKNOWN
    assert set(result.unknown_dimensions) == {"wind", "rain", "snow"}
    assert result.as_dict()["risk_label"] == "Unknown"


def test_partially_missing_dimensions_still_classify_known_values():
    result = assess_weather(wind_mph=40, rain_in_hr=None, snow_in_hr=None, load_weight_lb=42_000)
    assert result.risk == RiskLevel.SEVERE  # load override still applies
    assert set(result.unknown_dimensions) == {"rain", "snow"}


def test_midpoint_risk_mile_weighting():
    metrics = aggregate_segment_metrics(
        cumulative_miles=[0, 10, 20, 30],
        risks=[1, 5, 5, 3],
        duration_seconds=1_800,
    )
    assert metrics["no_travel_miles"] == pytest.approx(20.0)
    assert metrics["severe_miles"] == 0.0
    assert metrics["high_miles"] == pytest.approx(5.0)
    assert metrics["risk_miles"]["1"] == pytest.approx(5.0)
    assert metrics["average_risk_score"] == pytest.approx((5 * 1 + 20 * 5 + 5 * 3) / 30)


def test_ranking_lexicographic_order():
    metrics = [
        {
            "no_travel_miles": 0,
            "severe_miles": 20,
            "high_miles": 10,
            "average_risk_score": 3.1,
            "duration_seconds": 1,
        },
        {
            "no_travel_miles": 0,
            "severe_miles": 5,
            "high_miles": 100,
            "average_risk_score": 2.9,
            "duration_seconds": 2,
        },
        {
            "no_travel_miles": 2,
            "severe_miles": 0,
            "high_miles": 0,
            "average_risk_score": 1.0,
            "duration_seconds": 1,
        },
    ]
    assert rank_routes(metrics) == [1, 0, 2]
    assert ranking_key(metrics[0])[:2] == (0.0, 20.0)


def test_ranking_breaks_ties_by_duration_last():
    metrics = [
        {
            "no_travel_miles": 0,
            "severe_miles": 0,
            "high_miles": 0,
            "average_risk_score": 1.0,
            "duration_seconds": 900,
        },
        {
            "no_travel_miles": 0,
            "severe_miles": 0,
            "high_miles": 0,
            "average_risk_score": 1.0,
            "duration_seconds": 600,
        },
    ]
    assert rank_routes(metrics) == [1, 0]
