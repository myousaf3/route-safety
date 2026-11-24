from __future__ import annotations

import pytest

from core.services.geo import (
    cumulative_distances,
    decode_polyline,
    haversine_miles,
    sample_checkpoints,
    simplify_coordinates,
)


def test_haversine_chicago_to_denver():
    # ~920 miles great-circle
    distance = haversine_miles(41.8781, -87.6298, 39.7392, -104.9903)
    assert 880 < distance < 950


def test_cumulative_distances_and_sampling_endpoints():
    # A straight north-south line of roughly 69 miles per degree of latitude.
    coordinates = [[-87.0, 41.0], [-87.0, 42.0]]
    distances = cumulative_distances(coordinates)
    assert distances[0] == 0.0
    assert 68 < distances[-1] < 70

    points = sample_checkpoints(coordinates, 10)
    assert points[0].cumulative_miles == 0.0
    assert points[-1].cumulative_miles == pytest.approx(distances[-1], abs=0.01)
    assert len(points) == 8  # 0,10,...,60 plus the destination
    for previous, current in zip(points, points[1:], strict=False):
        assert current.cumulative_miles > previous.cumulative_miles
        assert current.cumulative_miles - previous.cumulative_miles <= 10.01


def test_sampling_includes_destination_when_exact_multiple():
    coordinates = [[-87.0, 41.0], [-87.0, 41.1]]
    total = cumulative_distances(coordinates)[-1]
    points = sample_checkpoints(coordinates, 10)
    assert points[-1].cumulative_miles == pytest.approx(total, abs=0.01)
    assert points[-1].lat == pytest.approx(41.1)


def test_simplify_keeps_endpoints_and_reduces_points():
    coordinates = [[-87.0 + i * 0.0001, 41.0] for i in range(101)]
    simplified = simplify_coordinates(coordinates, tolerance=0.001)
    assert len(simplified) == 2
    assert simplified[0] == coordinates[0]
    assert simplified[-1] == coordinates[-1]


def test_decode_polyline():
    # Google's canonical example: (38.5, -120.2), (40.7, -120.95), (43.252, -126.453)
    decoded = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", precision=5)
    assert decoded[0] == pytest.approx([-120.2, 38.5])
    assert decoded[1] == pytest.approx([-120.95, 40.7])
    assert decoded[2] == pytest.approx([-126.453, 43.252])
