"""Routing adapters: Valhalla (truck-aware alternatives) with an OSRM fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from core.errors import ProblemError
from core.services.geo import decode_polyline, simplify_coordinates
from core.services.http import ProviderError, request_json

logger = logging.getLogger(__name__)

MAX_ROUTES = 3


@dataclass
class RouteCandidate:
    geometry: list[list[float]]  # GeoJSON [lon, lat]
    distance_miles: float
    duration_seconds: float
    provider: str
    costing: str
    provider_route_index: int
    labels: list[str] = field(default_factory=list)


@dataclass
class RouteSet:
    routes: list[RouteCandidate]
    limitations: list[str]


def _valid_geometry(coordinates: list[list[float]]) -> bool:
    if len(coordinates) < 2:
        return False
    for point in coordinates:
        if len(point) < 2:
            return False
        lon, lat = point[0], point[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False
    return True


def _is_distinct(candidate: RouteCandidate, existing: list[RouteCandidate]) -> bool:
    for other in existing:
        distance_delta = abs(candidate.distance_miles - other.distance_miles) / max(
            other.distance_miles, 1.0
        )
        duration_delta = abs(candidate.duration_seconds - other.duration_seconds) / max(
            other.duration_seconds, 1.0
        )
        if distance_delta < 0.004 and duration_delta < 0.05:
            return False
    return True


def _valhalla_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    *,
    costing: str,
    load_weight_lb: int,
) -> list[RouteCandidate]:
    payload: dict[str, Any] = {
        "locations": [
            {"lat": origin[0], "lon": origin[1]},
            {"lat": destination[0], "lon": destination[1]},
        ],
        "costing": costing,
        "alternates": MAX_ROUTES,
        "directions_type": "none",
    }
    if costing == "truck":
        payload["costing_options"] = {
            "truck": {
                "height": 4.11,
                "width": 2.6,
                "length": 16.15,
                "weight": max(round(load_weight_lb * 0.00045359237, 2), 3.0),
                "axle_load": 15.0,
                "axle_count": 5,
            }
        }

    data = request_json(
        "POST",
        f"{settings.VALHALLA_BASE_URL}/route",
        provider="valhalla",
        json=payload,
        timeout=max(settings.HTTP_TIMEOUT_SECONDS, 35),
    )
    if isinstance(data, dict) and data.get("error"):
        raise ProviderError("valhalla", f"Valhalla rejected the route request: {data['error']}")

    candidates: list[RouteCandidate] = []
    trip = data.get("trip") if isinstance(data, dict) else None
    alternate_trips = data.get("alternates", []) if isinstance(data, dict) else []
    # Valhalla wraps each alternate as {"trip": {...}}; older responses return the trip directly.
    normalized_alternates = [
        alternate.get("trip", alternate) if isinstance(alternate, dict) else alternate
        for alternate in alternate_trips
    ]

    for index, trip_data in enumerate([trip, *normalized_alternates]):
        if not isinstance(trip_data, dict):
            continue
        legs = trip_data.get("legs") or []
        if not legs:
            continue
        shape = legs[0].get("shape")
        summary = trip_data.get("summary") or {}
        if not shape or "length" not in summary or "time" not in summary:
            continue
        try:
            geometry = (
                decode_polyline(shape, precision=6)
                if isinstance(shape, str)
                else [[float(p[0]), float(p[1])] for p in shape]
            )
        except (TypeError, ValueError, IndexError):
            continue
        if not _valid_geometry(geometry):
            continue
        geometry = simplify_coordinates(geometry)
        candidates.append(
            RouteCandidate(
                geometry=geometry,
                distance_miles=float(summary["length"]) * 0.621371,
                duration_seconds=float(summary["time"]),
                provider="valhalla",
                costing=costing,
                provider_route_index=index,
                labels=[f"Valhalla {costing}"],
            )
        )
    return candidates


def _osrm_routes(
    origin: tuple[float, float], destination: tuple[float, float]
) -> list[RouteCandidate]:
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{origin[1]:.6f},{origin[0]:.6f};{destination[1]:.6f},{destination[0]:.6f}"
    )
    data = request_json(
        "GET",
        url,
        provider="osrm",
        params={
            "alternatives": MAX_ROUTES,
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        },
    )
    candidates: list[RouteCandidate] = []
    if not isinstance(data, dict) or data.get("code") != "Ok":
        raise ProviderError("osrm", "OSRM could not calculate a route")
    for index, route in enumerate(data.get("routes", [])):
        geometry = (route.get("geometry") or {}).get("coordinates")
        if not _valid_geometry(geometry):
            continue
        geometry = simplify_coordinates(geometry)
        candidates.append(
            RouteCandidate(
                geometry=geometry,
                distance_miles=float(route["distance"]) / 1609.344,
                duration_seconds=float(route["duration"]),
                provider="osrm",
                costing="driving",
                provider_route_index=index,
                labels=["OSRM driving"],
            )
        )
    return candidates


def get_route_alternatives(
    origin: tuple[float, float],
    destination: tuple[float, float],
    load_weight_lb: int,
) -> RouteSet:
    """Return up to three distinct alternatives, documenting any shortfall."""

    limitations: list[str] = []
    routes: list[RouteCandidate] = []

    def absorb(candidates: list[RouteCandidate]) -> None:
        for candidate in candidates:
            if len(routes) >= MAX_ROUTES:
                return
            if _is_distinct(candidate, routes):
                routes.append(candidate)

    try:
        absorb(
            _valhalla_routes(origin, destination, costing="truck", load_weight_lb=load_weight_lb)
        )
    except ProviderError as exc:
        logger.warning("valhalla_truck_failed", extra={"error": exc.message})
        limitations.append(
            "Truck-costed routing was unavailable; routes use general-traffic costing."
        )

    if len(routes) < MAX_ROUTES:
        try:
            auto_routes = _valhalla_routes(
                origin, destination, costing="auto", load_weight_lb=load_weight_lb
            )
            before = len(routes)
            absorb(auto_routes)
            if len(routes) > before and any(r.costing == "truck" for r in routes):
                limitations.append(
                    "Only one truck-costed alternative was available; complementary "
                    "general-traffic alternatives are included."
                )
        except ProviderError as exc:
            logger.warning("valhalla_auto_failed", extra={"error": exc.message})

    if len(routes) < MAX_ROUTES:
        try:
            before = len(routes)
            absorb(_osrm_routes(origin, destination))
            if len(routes) > before:
                limitations.append("OSRM driving routes supplement the alternatives.")
        except ProviderError as exc:
            logger.warning("osrm_fallback_failed", extra={"error": exc.message})

    if not routes:
        raise ProblemError(
            code="no_routes",
            title="No viable routes",
            detail="The routing provider could not find a route between these locations.",
            status_code=422,
        )

    if len(routes) < MAX_ROUTES:
        limitations.append(
            f"The routing provider returned {len(routes)} distinct alternative(s); "
            "three distinct routes were not available for this origin/destination pair."
        )

    return RouteSet(routes=routes[:MAX_ROUTES], limitations=limitations)
