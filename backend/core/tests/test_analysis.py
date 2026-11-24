from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from core.models import RouteAnalysis
from core.services import analysis as analysis_service
from core.services import geocoding, routing
from core.services.geo import cumulative_distances
from core.services.risk import RiskLevel
from core.services.weather import WeatherSeries


def _line(
    start: tuple[float, float], end: tuple[float, float], count: int = 40
) -> list[list[float]]:
    """GeoJSON [lon, lat] straight line."""

    return [
        [
            start[1] + (end[1] - start[1]) * index / (count - 1),
            start[0] + (end[0] - start[0]) * index / (count - 1),
        ]
        for index in range(count)
    ]


def _route_candidate(index: int, *, speed_mph: float = 65.0) -> routing.RouteCandidate:
    lat_offset = (index - 1) * 0.4
    geometry = _line((41.8781 + lat_offset, -87.6298), (39.7392 + lat_offset, -104.9903))
    distance = cumulative_distances(geometry)[-1]
    return routing.RouteCandidate(
        geometry=geometry,
        distance_miles=distance,
        duration_seconds=distance / speed_mph * 3600,
        provider="valhalla",
        costing="truck",
        provider_route_index=index,
    )


def _mocked_routes() -> routing.RouteSet:
    return routing.RouteSet(
        routes=[
            _route_candidate(0, speed_mph=60),
            _route_candidate(1, speed_mph=65),
            _route_candidate(2, speed_mph=70),
        ],
        limitations=[],
    )


def _weather_factory(wind_for_lat):
    def fake_fetch(points, start, end):
        first_hour = start.replace(minute=0, second=0, microsecond=0)
        times = [first_hour + timedelta(hours=hour) for hour in range(0, 100)]
        series = []
        for lat, lon in points:
            wind = wind_for_lat(lat)
            series.append(
                WeatherSeries(
                    latitude=lat,
                    longitude=lon,
                    times=times,
                    wind=[wind] * len(times),
                    wind_gust=[wind] * len(times),
                    rain=[0.0] * len(times),
                    snow=[0.0] * len(times),
                    temperature=[50.0] * len(times),
                    visibility=[10.0] * len(times),
                    weather_code=[1] * len(times),
                )
            )
        return series

    return fake_fetch


@pytest.fixture
def patched_providers(monkeypatch):
    monkeypatch.setattr(
        geocoding,
        "geocode",
        lambda query: geocoding.Place(
            label=f"{query}, USA",
            lat=41.8781 if "Chicago" in query else 39.7392,
            lon=-87.6298 if "Chicago" in query else -104.9903,
            timezone="America/Chicago",
        ),
    )
    monkeypatch.setattr(routing, "get_route_alternatives", lambda *args, **kwargs: _mocked_routes())


@pytest.mark.django_db
def test_pipeline_persists_three_routes_and_ranks_by_duration(patched_providers, monkeypatch):
    monkeypatch.setattr(
        analysis_service, "fetch_weather_series", _weather_factory(lambda lat: 10.0)
    )
    departure = timezone.now() + timedelta(hours=2)

    result = analysis_service.run_analysis(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        departure_utc=departure,
        load_weight_lb=42_000,
        spacing_miles=25,
    )

    assert result.status == RouteAnalysis.Status.COMPLETED
    assert result.travel_advisory == "clear"
    assert result.routes.count() == 3

    routes = list(result.routes.order_by("rank"))
    # All low risk, so the fastest route wins the final tie-break.
    assert routes[0].recommended is True
    assert routes[0].duration_seconds == min(route.duration_seconds for route in routes)
    assert result.recommended_route_id == routes[0].id

    for route in routes:
        counts = {
            spacing: route.checkpoints.filter(spacing_miles=spacing).count()
            for spacing in (10, 25, 50)
        }
        assert counts[10] > 20
        assert counts[25] > 10
        assert counts[50] > 5
        assert route.metrics["severe_miles"] == 0
        assert route.metrics["no_travel_miles"] == 0
        checkpoints = list(route.checkpoints.filter(spacing_miles=10))
        assert checkpoints[0].cumulative_miles == 0
        assert checkpoints[-1].weather_status == "ok"
        assert all(point.risk == RiskLevel.LOW for point in checkpoints)
        assert route.hourly_risk["hours"] == 48
        assert len(route.hourly_risk["points"][0]["risk"]) == 49


@pytest.mark.django_db
def test_no_travel_everywhere_is_never_marked_safe(patched_providers, monkeypatch):
    monkeypatch.setattr(
        analysis_service, "fetch_weather_series", _weather_factory(lambda lat: 60.0)
    )

    result = analysis_service.run_analysis(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        departure_utc=timezone.now() + timedelta(hours=2),
        load_weight_lb=20_000,
        spacing_miles=10,
    )

    assert result.status == RouteAnalysis.Status.COMPLETED
    assert result.travel_advisory == "no_safe_route"
    assert result.recommended_route_id is None
    assert all(route.disqualified for route in result.routes.all())
    assert all(not route.recommended for route in result.routes.all())
    assert all(route.metrics["no_travel_miles"] > 0 for route in result.routes.all())


@pytest.mark.django_db
def test_load_override_is_applied_across_checkpoints(patched_providers, monkeypatch):
    monkeypatch.setattr(
        analysis_service, "fetch_weather_series", _weather_factory(lambda lat: 40.0)
    )

    result = analysis_service.run_analysis(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        departure_utc=timezone.now() + timedelta(hours=2),
        load_weight_lb=45_000,
        spacing_miles=25,
    )

    route = result.routes.order_by("rank").first()
    checkpoint = route.checkpoints.filter(spacing_miles=10).first()
    assert checkpoint.base_risk == RiskLevel.HIGH
    assert checkpoint.risk == RiskLevel.SEVERE
    assert any(reason["code"] == "load_wind_severe" for reason in checkpoint.reasons)
    assert result.travel_advisory == "caution"


@pytest.mark.django_db
def test_unknown_forecast_produces_partial_result(patched_providers, monkeypatch):
    def empty_series(points, start, end):
        return [
            WeatherSeries(
                latitude=lat,
                longitude=lon,
                times=[],
                wind=[],
                wind_gust=[],
                rain=[],
                snow=[],
                temperature=[],
                visibility=[],
                weather_code=[],
            )
            for lat, lon in points
        ]

    monkeypatch.setattr(analysis_service, "fetch_weather_series", empty_series)

    result = analysis_service.run_analysis(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        departure_utc=timezone.now() + timedelta(hours=2),
        load_weight_lb=42_000,
        spacing_miles=10,
    )

    assert result.status == RouteAnalysis.Status.PARTIAL
    checkpoint = result.routes.first().checkpoints.filter(spacing_miles=10).first()
    assert checkpoint.weather_status == "unknown"
    assert checkpoint.risk == RiskLevel.UNKNOWN
    assert checkpoint.risk_label == "Unknown"
    assert any("Unknown" in limitation for limitation in result.limitations)


@pytest.mark.django_db
def test_route_with_no_travel_is_disqualified_but_others_ranked(patched_providers, monkeypatch):
    # Route 2 sits furthest north and is the only one with no-travel wind.
    monkeypatch.setattr(
        analysis_service,
        "fetch_weather_series",
        _weather_factory(lambda lat: 60.0 if lat > 42.0 else 10.0),
    )

    result = analysis_service.run_analysis(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        departure_utc=timezone.now() + timedelta(hours=2),
        load_weight_lb=10_000,
        spacing_miles=25,
    )

    routes = {route.sequence: route for route in result.routes.all()}
    assert routes[2].disqualified is True
    assert routes[2].rank == 3
    assert routes[0].disqualified is False
    assert routes[1].disqualified is False
    assert result.travel_advisory in {"clear", "caution"}
    assert result.recommended_route_id in {routes[0].id, routes[1].id}


@pytest.mark.django_db
def test_past_departure_is_rejected_before_provider_calls(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("providers should not be called")

    monkeypatch.setattr(geocoding, "geocode", fail)

    with pytest.raises(Exception) as exc_info:
        analysis_service.run_analysis(
            origin_query="Chicago, IL",
            destination_query="Denver, CO",
            departure_utc=datetime.now(UTC) - timedelta(days=2),
            load_weight_lb=42_000,
            spacing_miles=25,
        )
    assert getattr(exc_info.value, "code", "") == "departure_in_past"
