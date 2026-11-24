from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from core.models import Checkpoint, RouteAnalysis, RouteOption

pytestmark = pytest.mark.django_db


def seed() -> str:
    output = StringIO()
    call_command("seed_demo", stdout=output)
    return output.getvalue()


def test_seed_demo_creates_complete_reusable_analysis():
    seed()

    analyses = RouteAnalysis.objects.filter(request_fingerprint="demo-seed-v1")
    assert analyses.count() == 1
    analysis = analyses.get()
    assert analysis.status == RouteAnalysis.Status.COMPLETED
    assert analysis.recommended_route is not None
    assert analysis.providers["routing"] == "Valhalla"
    assert "demo" in analysis.limitations[-1].lower()

    routes = RouteOption.objects.filter(analysis=analysis)
    assert routes.count() == 3
    assert routes.filter(recommended=True).get() == analysis.recommended_route
    assert set(routes.values_list("rank", flat=True)) == {1, 2, 3}
    assert all(route.metrics["distance_miles"] > 0 for route in routes)
    assert all(route.hourly_risk["hours"] == 48 for route in routes)

    route = routes.get(sequence=0)
    assert Checkpoint.objects.filter(route=route, spacing_miles=10).exists()
    assert Checkpoint.objects.filter(route=route, spacing_miles=25).exists()
    assert Checkpoint.objects.filter(route=route, spacing_miles=50).exists()


def test_seed_demo_is_idempotent():
    seed()
    checkpoint_count = Checkpoint.objects.count()
    seed()

    assert checkpoint_count > 0
    assert RouteAnalysis.objects.filter(request_fingerprint="demo-seed-v1").count() == 1
    assert RouteOption.objects.count() == 3
    assert Checkpoint.objects.count() == checkpoint_count
