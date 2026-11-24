"""Geometry helpers: distance, interpolation, checkpoint sampling, time zones."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class SamplePoint:
    lat: float
    lon: float
    cumulative_miles: float


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def cumulative_distances(coordinates: list[list[float]]) -> list[float]:
    """Cumulative miles for GeoJSON [lon, lat] coordinate pairs."""

    if not coordinates:
        return []
    distances = [0.0]
    for index in range(1, len(coordinates)):
        lon1, lat1 = coordinates[index - 1][0], coordinates[index - 1][1]
        lon2, lat2 = coordinates[index][0], coordinates[index][1]
        distances.append(distances[-1] + haversine_miles(lat1, lon1, lat2, lon2))
    return distances


def _interpolate(start: list[float], end: list[float], ratio: float) -> tuple[float, float]:
    lon = start[0] + (end[0] - start[0]) * ratio
    lat = start[1] + (end[1] - start[1]) * ratio
    return lat, lon


def sample_checkpoints(coordinates: list[list[float]], spacing_miles: int) -> list[SamplePoint]:
    """Sample points at a fixed cumulative mileage interval, including both endpoints."""

    if spacing_miles <= 0:
        raise ValueError("spacing_miles must be positive")
    if len(coordinates) < 2:
        raise ValueError("route geometry needs at least two coordinates")

    cumulative = cumulative_distances(coordinates)
    total_miles = cumulative[-1]
    points: list[SamplePoint] = []

    # Origin.
    points.append(SamplePoint(lat=coordinates[0][1], lon=coordinates[0][0], cumulative_miles=0.0))

    target = float(spacing_miles)
    segment_index = 1
    while target < total_miles - 0.05:
        while segment_index < len(cumulative) and cumulative[segment_index] < target:
            segment_index += 1
        if segment_index >= len(coordinates):
            break
        segment_start = cumulative[segment_index - 1]
        segment_end = cumulative[segment_index]
        span = segment_end - segment_start
        ratio = 0.0 if span <= 0 else (target - segment_start) / span
        lat, lon = _interpolate(coordinates[segment_index - 1], coordinates[segment_index], ratio)
        points.append(SamplePoint(lat=lat, lon=lon, cumulative_miles=target))
        target += spacing_miles

    destination = coordinates[-1]
    if total_miles - points[-1].cumulative_miles > 0.05:
        points.append(
            SamplePoint(lat=destination[1], lon=destination[0], cumulative_miles=total_miles)
        )
    elif points:
        # Replace the final sample with the exact destination to avoid a near-duplicate.
        points[-1] = SamplePoint(
            lat=destination[1], lon=destination[0], cumulative_miles=total_miles
        )

    return points


@lru_cache(maxsize=1)
def _timezone_finder():
    try:
        from timezonefinder import TimezoneFinder

        return TimezoneFinder(in_memory=True)
    except Exception:  # pragma: no cover - optional dependency/runtime issue
        return None


def timezone_for(lat: float, lon: float) -> str:
    finder = _timezone_finder()
    if finder is None:
        return "UTC"
    try:
        return finder.timezone_at(lat=lat, lng=lon) or "UTC"
    except Exception:  # pragma: no cover
        return "UTC"


def decode_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
    """Decode a Google/Valhalla encoded polyline into GeoJSON [lon, lat] pairs."""

    index = 0
    lat = 0
    lon = 0
    coordinates: list[list[float]] = []
    factor = 10**precision
    length = len(encoded)

    while index < length:
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lon += ~(result >> 1) if result & 1 else result >> 1

        coordinates.append([lon / factor, lat / factor])

    return coordinates


def _point_segment_distance(point: list[float], start: list[float], end: list[float]) -> float:
    px, py = point[0], point[1]
    ax, ay = start[0], start[1]
    bx, by = end[0], end[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify_coordinates(
    coordinates: list[list[float]], tolerance: float = 0.0007
) -> list[list[float]]:
    """Ramer-Douglas-Peucker simplification in lon/lat space for compact responses."""

    if len(coordinates) <= 2:
        return coordinates

    keep = [False] * len(coordinates)
    keep[0] = keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(coordinates) - 1)]
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        max_distance = 0.0
        max_index = first
        for index in range(first + 1, last):
            distance = _point_segment_distance(
                coordinates[index], coordinates[first], coordinates[last]
            )
            if distance > max_distance:
                max_distance = distance
                max_index = index
        if max_distance > tolerance:
            keep[max_index] = True
            stack.append((first, max_index))
            stack.append((max_index, last))

    simplified = [point for point, keep_point in zip(coordinates, keep, strict=False) if keep_point]
    return simplified if len(simplified) >= 2 else coordinates


def route_bounds(coordinates: list[list[float]]) -> list[list[float]]:
    """[[min_lon, min_lat], [max_lon, max_lat]] for fitBounds."""

    lons = [point[0] for point in coordinates]
    lats = [point[1] for point in coordinates]
    return [[min(lons), min(lats)], [max(lons), max(lats)]]
