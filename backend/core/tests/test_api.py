from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from core.models import Checkpoint, RouteAnalysis, RouteOption
from core.services.weather import WeatherSeries, _series_from_payload

pytestmark = pytest.mark.django_db


def _make_analysis(*, recommended: bool = True, status: str = "completed") -> RouteAnalysis:
    now = datetime.now(UTC)
    analysis = RouteAnalysis.objects.create(
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        origin_label="Chicago, Cook County, Illinois, USA",
        destination_label="Denver, Denver County, Colorado, USA",
        origin_lat=41.8781,
        origin_lon=-87.6298,
        destination_lat=39.7392,
        destination_lon=-104.9903,
        origin_timezone="America/Chicago",
        destination_timezone="America/Denver",
        departure_utc=now + timedelta(hours=2),
        load_weight_lb=42_000,
        spacing_miles=25,
        status=status,
        travel_advisory="clear",
        providers={"routing": "VALHALLA", "weather": "Open-Meteo"},
        limitations=[],
        risk_policy_version="2026-11-a",
    )
    route = RouteOption.objects.create(
        analysis=analysis,
        sequence=0,
        rank=1,
        recommended=recommended,
        disqualified=False,
        distance_miles=1005.0,
        duration_seconds=54_000,
        eta_utc=now + timedelta(hours=17),
        geometry={"type": "LineString", "coordinates": [[-87.6298, 41.8781], [-104.9903, 39.7392]]},
        metrics={
            "no_travel_miles": 0,
            "severe_miles": 2.5,
            "high_miles": 10.0,
            "average_risk_score": 1.3,
            "max_risk": 4,
            "duration_seconds": 54_000,
        },
        hourly_risk={
            "start_utc": (now + timedelta(hours=2)).isoformat(),
            "hours": 48,
            "step_hours": 1,
            "points": [{"lat": 41.8781, "lon": -87.6298, "cumulative_miles": 0, "risk": [1] * 49}],
        },
    )
    for spacing, count in ((10, 3), (25, 2), (50, 2)):
        for sequence in range(count):
            Checkpoint.objects.create(
                route=route,
                spacing_miles=spacing,
                sequence=sequence,
                cumulative_miles=sequence * spacing,
                lat=41.8781,
                lon=-87.6298,
                eta_utc=now + timedelta(hours=2 + sequence),
                timezone="America/Chicago",
                weather={"wind_mph": 10.0, "rain_in_hr": 0.0, "snow_in_hr": 0.0},
                weather_status="ok",
                base_risk=1,
                risk=1,
                risk_label="Low",
                reasons=[],
            )
    if recommended:
        analysis.recommended_route_id = route.id
        analysis.save(update_fields=["recommended_route"])
    return analysis


def test_create_endpoint_returns_full_payload(monkeypatch):
    analysis = _make_analysis()
    monkeypatch.setattr("core.views.create_queued_analysis", lambda **kwargs: analysis)
    monkeypatch.setattr("core.views.process_analysis_task.delay", lambda *args, **kwargs: None)
    client = APIClient()

    response = client.post(
        "/api/v1/analyses/",
        {
            "origin": "Chicago, IL",
            "destination": "Denver, CO",
            "departure": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "load_weight_lb": 42_000,
            "spacing_miles": 25,
        },
        format="json",
    )
    assert response.status_code == 202
    body = response.json()
    assert body["id"] == str(analysis.id)
    assert body["recommended_route_id"] is not None
    assert len(body["routes"]) == 1
    route = body["routes"][0]
    assert route["recommended"] is True
    assert set(route["checkpoints"].keys()) == {"10", "25", "50"}
    assert len(route["checkpoints"]["10"]) == 3
    assert route["heatmap"]["hours"] == 48


def test_validation_rejects_identical_endpoints():
    client = APIClient()
    response = client.post(
        "/api/v1/analyses/",
        {
            "origin": "Denver, CO",
            "destination": "denver, co",
            "departure": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "load_weight_lb": 42_000,
        },
        format="json",
    )
    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid"


def test_validation_rejects_out_of_range_weight():
    client = APIClient()
    response = client.post(
        "/api/v1/analyses/",
        {
            "origin": "Chicago, IL",
            "destination": "Denver, CO",
            "departure": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "load_weight_lb": 500_000,
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["errors"]["load_weight_lb"]


def test_past_departure_returns_problem_details():
    client = APIClient()
    response = client.post(
        "/api/v1/analyses/",
        {
            "origin": "Chicago, IL",
            "destination": "Denver, CO",
            "departure": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            "load_weight_lb": 42_000,
        },
        format="json",
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "departure_in_past"
    assert body["correlation_id"]


def test_analysis_detail_and_delete():
    analysis = _make_analysis()
    client = APIClient()

    detail = client.get(f"/api/v1/analyses/{analysis.id}/")
    assert detail.status_code == 200
    assert detail.json()["request"]["origin"]["query"] == "Chicago, IL"
    assert detail.json()["travel_advisory"] == "clear"

    deleted = client.delete(f"/api/v1/analyses/{analysis.id}/")
    assert deleted.status_code == 204
    assert not RouteAnalysis.objects.filter(pk=analysis.pk).exists()


def test_history_list_and_invalid_filter():
    _make_analysis()
    client = APIClient()

    listed = client.get("/api/v1/analyses/")
    assert listed.status_code == 200
    assert len(listed.json()["results"]) == 1
    assert listed.json()["results"][0]["route_count"] == 1

    invalid = client.get("/api/v1/analyses/?status=bogus")
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_status_filter"


def test_place_search_short_query_does_not_call_provider():
    client = APIClient()
    response = client.get("/api/v1/places/?q=ch")
    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_health_and_metrics_endpoints():
    client = APIClient()
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.content.decode()


def test_policy_endpoint_exposes_thresholds():
    client = APIClient()
    response = client.get("/api/v1/policy/")
    assert response.status_code == 200
    body = response.json()
    assert body["thresholds"]["wind_mph"]["no_travel"] == ">=55"
    assert body["ranking_key"][0] == "no_travel_miles"


def test_weather_normalization_and_sampling():
    payload = {
        "hourly": {
            "time": ["2026-11-23T00:00", "2026-11-23T01:00"],
            "wind_speed_10m": [12.0, 13.0],
            "wind_gusts_10m": [20.0, 21.0],
            "rain": [0.1, 0.0],
            "showers": [0.05, 0.02],
            "snowfall": [2.54, 0.0],
            "temperature_2m": [32.0, 33.0],
            "visibility": [1609.344, 8046.72],
            "weather_code": [61, 3],
        }
    }
    series = _series_from_payload(payload, 41.0, -87.0)
    assert series.rain[0] == pytest.approx(0.15)
    assert series.snow[0] == pytest.approx(1.0)
    assert series.visibility[0] == pytest.approx(1.0)

    sample = series.sample(datetime(2026, 11, 23, 0, 20, tzinfo=UTC))
    assert sample.wind_mph == 12.0
    assert sample.status == "ok"

    out_of_range = series.sample(datetime(2026, 11, 24, 0, 0, tzinfo=UTC))
    assert out_of_range.status == "unknown"
    assert out_of_range.wind_mph is None


def test_weather_series_all_missing_is_unknown():
    series = WeatherSeries(
        latitude=41.0,
        longitude=-87.0,
        times=[datetime(2026, 11, 23, tzinfo=UTC)],
        wind=[None],
        wind_gust=[None],
        rain=[None],
        snow=[None],
        temperature=[None],
        visibility=[None],
        weather_code=[None],
    )
    assert series.sample(datetime(2026, 11, 23, tzinfo=UTC)).status == "unknown"
