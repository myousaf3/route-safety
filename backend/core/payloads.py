"""Response assembly for analysis detail and route data."""

from __future__ import annotations

from typing import Any

from core.models import Checkpoint, RouteAnalysis, RouteOption


def _checkpoint_payload(checkpoint: Checkpoint) -> dict[str, Any]:
    return {
        "sequence": checkpoint.sequence,
        "cumulative_miles": checkpoint.cumulative_miles,
        "lat": checkpoint.lat,
        "lon": checkpoint.lon,
        "eta_utc": checkpoint.eta_utc.isoformat(),
        "timezone": checkpoint.timezone,
        "weather": checkpoint.weather,
        "weather_status": checkpoint.weather_status,
        "base_risk": checkpoint.base_risk,
        "risk": checkpoint.risk,
        "risk_label": checkpoint.risk_label,
        "reasons": checkpoint.reasons,
    }


def _route_payload(
    route: RouteOption, checkpoints: list[Checkpoint], *, recommended_route_id: int | None
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {"10": [], "25": [], "50": []}
    for checkpoint in checkpoints:
        grouped.setdefault(str(checkpoint.spacing_miles), []).append(
            _checkpoint_payload(checkpoint)
        )

    return {
        "id": route.id,
        "sequence": route.sequence,
        "rank": route.rank,
        "recommended": route.id == recommended_route_id and route.recommended,
        "disqualified": route.disqualified,
        "distance_miles": route.distance_miles,
        "duration_seconds": route.duration_seconds,
        "eta_utc": route.eta_utc.isoformat(),
        "geometry": route.geometry,
        "metrics": route.metrics,
        "provider": route.provider,
        "costing": route.costing,
        "checkpoints": grouped,
        "heatmap": route.hourly_risk,
    }


def analysis_detail_payload(analysis: RouteAnalysis) -> dict[str, Any]:
    routes = list(analysis.routes.all())
    recommended_route_id = analysis.recommended_route_id
    least_hazardous_route_id = None
    if routes:
        least_hazardous_route_id = min(routes, key=lambda route: route.rank).id

    return {
        "id": str(analysis.id),
        "status": analysis.status,
        "created_at": analysis.created_at.isoformat(),
        "travel_advisory": analysis.travel_advisory,
        "recommended_route_id": recommended_route_id,
        "least_hazardous_route_id": least_hazardous_route_id,
        "limitations": analysis.limitations,
        "risk_policy_version": analysis.risk_policy_version,
        "providers": analysis.providers,
        "error": analysis.error,
        "request": {
            "origin": {
                "query": analysis.origin_query,
                "label": analysis.origin_label,
                "lat": analysis.origin_lat,
                "lon": analysis.origin_lon,
                "timezone": analysis.origin_timezone,
            },
            "destination": {
                "query": analysis.destination_query,
                "label": analysis.destination_label,
                "lat": analysis.destination_lat,
                "lon": analysis.destination_lon,
                "timezone": analysis.destination_timezone,
            },
            "departure_utc": analysis.departure_utc.isoformat(),
            "departure_timezone": analysis.origin_timezone,
            "load_weight_lb": analysis.load_weight_lb,
            "spacing_miles": analysis.spacing_miles,
        },
        "routes": [
            _route_payload(
                route, list(route.checkpoints.all()), recommended_route_id=recommended_route_id
            )
            for route in routes
        ],
    }
