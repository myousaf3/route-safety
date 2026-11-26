"""End-to-end analysis pipeline: geocode -> route -> sample -> weather -> risk -> rank."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.errors import ProblemError
from core.models import AnalysisEvent, Checkpoint, RouteAnalysis, RouteOption
from core.services import geocoding, routing
from core.services.geo import cumulative_distances, sample_checkpoints, timezone_for
from core.services.risk import (
    RISK_LABELS,
    RiskLevel,
    aggregate_segment_metrics,
    assess_weather,
    rank_routes,
)
from core.services.weather import WeatherIndex, fetch_weather_series

logger = logging.getLogger(__name__)

SPACINGS = (10, 25, 50)
RANKING_SPACING = 10
HEATMAP_HOURS = 48
HEATMAP_STEP_HOURS = 1
MAX_DEPARTURE_DAYS = 15
MAX_WEIGHT_LB = 120_000
PROVIDER_LABELS = {"valhalla": "Valhalla", "osrm": "OSRM"}


@dataclass
class CheckpointDraft:
    sequence: int
    cumulative_miles: float
    lat: float
    lon: float
    eta_utc: datetime
    timezone: str
    weather: dict
    weather_status: str
    base_risk: int
    risk: int
    risk_label: str
    reasons: list[dict]


@dataclass
class RouteDraft:
    candidate: routing.RouteCandidate
    checkpoints: dict[int, list[CheckpointDraft]]
    metrics: dict
    heatmap: dict


def _validate_departure(departure_utc: datetime) -> None:
    now = timezone.now()
    if departure_utc < now - timedelta(hours=2):
        raise ProblemError(
            code="departure_in_past",
            title="Departure time is in the past",
            detail="Choose a departure time between now and 15 days from now.",
            status_code=422,
        )
    if departure_utc > now + timedelta(days=MAX_DEPARTURE_DAYS):
        raise ProblemError(
            code="departure_out_of_horizon",
            title="Departure is outside the forecast horizon",
            detail="Forecast data is available for departures up to 15 days ahead.",
            status_code=422,
        )


def _timezone_cached(lat: float, lon: float, cache: dict[tuple[float, float], str]) -> str:
    key = (round(lat, 2), round(lon, 2))
    if key not in cache:
        cache[key] = timezone_for(lat, lon)
    return cache[key]


def _weather_coordinates(route_drafts: list[RouteDraft]) -> list[tuple[float, float]]:
    seen: dict[str, tuple[float, float]] = {}
    for route in route_drafts:
        for points in route.checkpoints.values():
            for point in points:
                key = f"{point.lat:.5f},{point.lon:.5f}"
                seen[key] = (point.lat, point.lon)
    return list(seen.values())


def _execute_analysis(analysis: RouteAnalysis) -> None:
    origin_query = analysis.origin_query
    destination_query = analysis.destination_query
    departure_utc = analysis.departure_utc
    load_weight_lb = analysis.load_weight_lb
    spacing_miles = analysis.spacing_miles

    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=UTC)
    departure_utc = departure_utc.astimezone(UTC)
    analysis.departure_utc = departure_utc

    _validate_departure(departure_utc)

    analysis.status = RouteAnalysis.Status.ROUTING
    analysis.save(update_fields=["status", "departure_utc"])

    origin = geocoding.geocode(origin_query)
    destination = geocoding.geocode(destination_query)

    from core.services.geo import haversine_miles

    if haversine_miles(origin.lat, origin.lon, destination.lat, destination.lon) < 0.5:
        raise ProblemError(
            code="identical_endpoints",
            title="Origin and destination are the same",
            detail="Choose two different locations more than half a mile apart.",
            status_code=422,
        )

    route_set = routing.get_route_alternatives(
        (origin.lat, origin.lon),
        (destination.lat, destination.lon),
        load_weight_lb=load_weight_lb,
    )
    limitations = list(route_set.limitations)

    analysis.status = RouteAnalysis.Status.WEATHER
    analysis.save(update_fields=["status"])

    timezone_cache: dict[tuple[float, float], str] = {}

    def build_checkpoints(route: routing.RouteCandidate) -> dict[int, list[CheckpointDraft]]:
        shape_total = cumulative_distances(route.geometry)[-1]
        provider_distance = max(route.distance_miles, 0.1)
        drafts: dict[int, list[CheckpointDraft]] = {}
        for spacing in SPACINGS:
            samples = sample_checkpoints(route.geometry, spacing)
            points: list[CheckpointDraft] = []
            for index, sample in enumerate(samples):
                # Normalize sampled geometry distance to the provider's road mileage so
                # displayed mileage and risk-mile totals match the route summary.
                fraction = (
                    min(sample.cumulative_miles / shape_total, 1.0) if shape_total > 0 else 0.0
                )
                cumulative_miles = fraction * provider_distance
                eta = departure_utc + timedelta(seconds=route.duration_seconds * fraction)
                points.append(
                    CheckpointDraft(
                        sequence=index,
                        cumulative_miles=round(cumulative_miles, 2),
                        lat=sample.lat,
                        lon=sample.lon,
                        eta_utc=eta,
                        timezone=_timezone_cached(sample.lat, sample.lon, timezone_cache),
                        weather={},
                        weather_status="pending",
                        base_risk=0,
                        risk=0,
                        risk_label="Unknown",
                        reasons=[],
                    )
                )
            drafts[spacing] = points
        return drafts

    drafts = [
        RouteDraft(
            candidate=candidate,
            checkpoints=build_checkpoints(candidate),
            metrics={},
            heatmap={},
        )
        for candidate in route_set.routes
    ]

    max_duration = max(route.candidate.duration_seconds for route in drafts)
    weather_start = departure_utc - timedelta(hours=1)
    weather_end = departure_utc + timedelta(
        seconds=max(max_duration + 6 * 3600, (HEATMAP_HOURS + 3) * 3600)
    )
    coordinates = _weather_coordinates(drafts)

    try:
        series = fetch_weather_series(coordinates, weather_start, weather_end)
    except Exception as exc:  # ProviderError or unexpected adapter failure
        logger.exception("weather_fetch_failed", extra={"error_code": type(exc).__name__})
        limitations.append("Forecast data could not be fully retrieved; weather is unknown.")
        series = []
        weather_index = None
    else:
        weather_index = WeatherIndex(series, coordinates)

    unknown_total = 0

    for route in drafts:
        route_points = route.checkpoints[10]

        for spacing, points in route.checkpoints.items():
            for point in points:
                sample = (
                    weather_index.sample(point.lat, point.lon, point.eta_utc)
                    if weather_index
                    else None
                )
                if sample is None or sample.status == "unknown":
                    point.weather = {}
                    point.weather_status = "unknown"
                    assessment = assess_weather(
                        wind_mph=None,
                        rain_in_hr=None,
                        snow_in_hr=None,
                        load_weight_lb=load_weight_lb,
                    )
                    if spacing == RANKING_SPACING:
                        unknown_total += 1
                else:
                    point.weather = sample.as_dict()
                    point.weather_status = "ok"
                    assessment = assess_weather(
                        wind_mph=sample.wind_mph,
                        rain_in_hr=sample.rain_in_hr,
                        snow_in_hr=sample.snow_in_hr,
                        load_weight_lb=load_weight_lb,
                    )
                point.base_risk = int(assessment.base_risk)
                point.risk = int(assessment.risk)
                point.risk_label = assessment.label
                point.reasons = [
                    {
                        "code": reason.code,
                        "dimension": reason.dimension,
                        "message": reason.message,
                        "risk": reason.risk,
                    }
                    for reason in assessment.reasons
                ]

        route.metrics = aggregate_segment_metrics(
            cumulative_miles=[point.cumulative_miles for point in route_points],
            risks=[point.risk for point in route_points],
            duration_seconds=route.candidate.duration_seconds,
        )
        route.metrics["distance_miles"] = round(route.candidate.distance_miles, 2)

        heatmap_points: list[dict] = []
        for point in route_points:
            risks: list[int] = []
            for hour in range(0, HEATMAP_HOURS + 1, HEATMAP_STEP_HOURS):
                when = departure_utc + timedelta(hours=hour)
                if weather_index is None:
                    risks.append(int(RiskLevel.UNKNOWN))
                    continue
                sample = weather_index.sample(point.lat, point.lon, when)
                if sample.status == "unknown":
                    risks.append(int(RiskLevel.UNKNOWN))
                else:
                    assessment = assess_weather(
                        wind_mph=sample.wind_mph,
                        rain_in_hr=sample.rain_in_hr,
                        snow_in_hr=sample.snow_in_hr,
                        load_weight_lb=load_weight_lb,
                    )
                    risks.append(int(assessment.risk))
            heatmap_points.append(
                {
                    "lat": point.lat,
                    "lon": point.lon,
                    "cumulative_miles": round(point.cumulative_miles, 2),
                    "risk": risks,
                }
            )

        route.heatmap = {
            "start_utc": departure_utc.isoformat(),
            "hours": HEATMAP_HOURS,
            "step_hours": HEATMAP_STEP_HOURS,
            "points": heatmap_points,
        }

    analysis.status = RouteAnalysis.Status.SCORING
    analysis.save(update_fields=["status"])

    ranked_indices = rank_routes([route.metrics for route in drafts])
    disqualified = [route.metrics.get("no_travel_miles", 0.0) > 0.01 for route in drafts]
    any_safe = any(not flag for flag in disqualified)

    if not any_safe:
        advisory = "no_safe_route"
        recommended_index: int | None = None
    else:
        recommended_index = next(index for index in ranked_indices if not disqualified[index])
        best_risk = int(drafts[recommended_index].metrics.get("max_risk", 0))
        advisory = "caution" if best_risk >= int(RiskLevel.HIGH) else "clear"

    if unknown_total:
        limitations.append(
            f"{unknown_total} checkpoint forecast(s) were unavailable and marked Unknown; "
            "unknown weather is never treated as safe or as zero precipitation."
        )
    if len(drafts) < 3:
        limitations.append(
            "Fewer than three distinct route alternatives were available from the provider."
        )

    routing_providers = sorted({route.candidate.provider for route in drafts})
    routing_labels = [
        PROVIDER_LABELS.get(provider, provider.title()) for provider in routing_providers
    ]
    status = RouteAnalysis.Status.PARTIAL if unknown_total else RouteAnalysis.Status.COMPLETED

    with transaction.atomic():
        analysis.origin_label = origin.label
        analysis.destination_label = destination.label
        analysis.origin_lat = origin.lat
        analysis.origin_lon = origin.lon
        analysis.destination_lat = destination.lat
        analysis.destination_lon = destination.lon
        analysis.origin_timezone = origin.timezone
        analysis.destination_timezone = destination.timezone
        analysis.departure_utc = departure_utc
        analysis.load_weight_lb = load_weight_lb
        analysis.spacing_miles = spacing_miles
        analysis.status = status
        analysis.travel_advisory = advisory
        analysis.providers = {
            "geocoding": "Nominatim / OpenStreetMap",
            "routing": ", ".join(routing_labels),
            "weather": "Open-Meteo",
            "risk_policy_version": settings.RISK_POLICY_VERSION,
        }
        analysis.limitations = limitations
        analysis.risk_policy_version = settings.RISK_POLICY_VERSION
        analysis.save()

        route_rows: list[RouteOption] = []
        for sequence, route in enumerate(drafts):
            rank = ranked_indices.index(sequence) + 1
            route_rows.append(
                RouteOption(
                    analysis=analysis,
                    sequence=sequence,
                    rank=rank,
                    recommended=recommended_index == sequence,
                    disqualified=disqualified[sequence],
                    distance_miles=round(route.candidate.distance_miles, 2),
                    duration_seconds=round(route.candidate.duration_seconds, 1),
                    eta_utc=departure_utc + timedelta(seconds=route.candidate.duration_seconds),
                    geometry={"type": "LineString", "coordinates": route.candidate.geometry},
                    metrics=route.metrics,
                    hourly_risk=route.heatmap,
                    provider=route.candidate.provider,
                    costing=route.candidate.costing,
                    provider_route_index=route.candidate.provider_route_index,
                )
            )
        RouteOption.objects.bulk_create(route_rows)

        checkpoint_rows: list[Checkpoint] = []
        for route_row, route in zip(route_rows, drafts, strict=False):
            for spacing, points in route.checkpoints.items():
                for point in points:
                    checkpoint_rows.append(
                        Checkpoint(
                            route=route_row,
                            spacing_miles=spacing,
                            sequence=point.sequence,
                            cumulative_miles=point.cumulative_miles,
                            lat=point.lat,
                            lon=point.lon,
                            eta_utc=point.eta_utc,
                            timezone=point.timezone,
                            weather=point.weather,
                            weather_status=point.weather_status,
                            base_risk=point.base_risk,
                            risk=point.risk,
                            risk_label=point.risk_label,
                            reasons=point.reasons,
                        )
                    )
        Checkpoint.objects.bulk_create(checkpoint_rows, batch_size=500)

        recommended_id = route_rows[recommended_index].id if recommended_index is not None else None
        analysis.recommended_route_id = recommended_id
        analysis.save(update_fields=["recommended_route", "updated_at"])

        AnalysisEvent.objects.bulk_create(
            [
                AnalysisEvent(
                    analysis=analysis,
                    stage="queued",
                    message="Analysis accepted",
                ),
                AnalysisEvent(
                    analysis=analysis,
                    stage="routing",
                    message=f"{len(drafts)} route alternative(s) calculated",
                    data={"providers": routing_providers},
                ),
                AnalysisEvent(
                    analysis=analysis,
                    stage="weather",
                    message=f"Forecast sampled at {len(coordinates)} corridor coordinates",
                    data={"spacing_miles": list(SPACINGS), "unknown_checkpoints": unknown_total},
                ),
                AnalysisEvent(
                    analysis=analysis,
                    stage="scoring",
                    message=f"Risk policy {settings.RISK_POLICY_VERSION} applied",
                    data={"ranking_spacing_miles": RANKING_SPACING},
                ),
                AnalysisEvent(
                    analysis=analysis,
                    stage="completed" if status == RouteAnalysis.Status.COMPLETED else "partial",
                    message=(
                        "Analysis completed"
                        if status == RouteAnalysis.Status.COMPLETED
                        else "Analysis completed with forecast gaps"
                    ),
                    data={"travel_advisory": advisory},
                ),
            ]
        )

    logger.info(
        "analysis_completed",
        extra={
            "analysis_id": str(analysis.id),
            "status": status,
            "routes": len(drafts),
            "unknown_checkpoints": unknown_total,
        },
    )
    return


def process_analysis(analysis_id) -> RouteAnalysis:
    """Run the full pipeline for a persisted (queued) analysis.

    Updates the analysis row in place and marks it FAILED on any error so callers
    polling the API can observe the terminal state.
    """

    analysis = RouteAnalysis.objects.get(pk=analysis_id)
    try:
        _execute_analysis(analysis)
    except ProblemError as exc:
        analysis.status = RouteAnalysis.Status.FAILED
        analysis.error = {"code": exc.code, "title": exc.title, "detail": exc.detail}
        analysis.save(update_fields=["status", "error"])
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("analysis_failed", extra={"analysis_id": str(analysis.id)})
        analysis.status = RouteAnalysis.Status.FAILED
        analysis.error = {
            "code": "analysis_failed",
            "title": "Analysis failed",
            "detail": str(exc),
        }
        analysis.save(update_fields=["status", "error"])
        raise
    analysis.refresh_from_db()
    return analysis


def create_queued_analysis(
    *,
    origin_query: str,
    destination_query: str,
    departure_utc: datetime,
    load_weight_lb: int,
    spacing_miles: int,
    owner=None,
) -> RouteAnalysis:
    """Persist a queued analysis row for asynchronous processing."""

    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=UTC)
    departure_utc = departure_utc.astimezone(UTC)
    return RouteAnalysis.objects.create(
        owner=owner,
        origin_query=origin_query,
        destination_query=destination_query,
        origin_label=origin_query,
        destination_label=destination_query,
        origin_lat=0.0,
        origin_lon=0.0,
        destination_lat=0.0,
        destination_lon=0.0,
        origin_timezone="UTC",
        destination_timezone="UTC",
        departure_utc=departure_utc,
        load_weight_lb=load_weight_lb,
        spacing_miles=spacing_miles,
        status=RouteAnalysis.Status.QUEUED,
    )


def run_analysis(
    *,
    origin_query: str,
    destination_query: str,
    departure_utc: datetime,
    load_weight_lb: int,
    spacing_miles: int,
    owner=None,
) -> RouteAnalysis:
    """Synchronous entry point: persist a queued analysis and run it inline."""

    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=UTC)
    departure_utc = departure_utc.astimezone(UTC)

    analysis = RouteAnalysis.objects.create(
        owner=owner,
        origin_query=origin_query,
        destination_query=destination_query,
        origin_label=origin_query,
        destination_label=destination_query,
        origin_lat=0.0,
        origin_lon=0.0,
        destination_lat=0.0,
        destination_lon=0.0,
        origin_timezone="UTC",
        destination_timezone="UTC",
        departure_utc=departure_utc,
        load_weight_lb=load_weight_lb,
        spacing_miles=spacing_miles,
        status=RouteAnalysis.Status.QUEUED,
    )
    process_analysis(analysis.id)
    analysis.refresh_from_db()
    return analysis


def risk_legend() -> list[dict]:
    return [{"value": int(level), "label": RISK_LABELS[level]} for level in RiskLevel]
