"""Authentication and per-user visibility tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.models import RouteAnalysis

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "StrongPass123!"


def _analysis(owner=None) -> RouteAnalysis:
    now = datetime.now(UTC)
    return RouteAnalysis.objects.create(
        owner=owner,
        origin_query="Chicago, IL",
        destination_query="Denver, CO",
        origin_label="Chicago, IL",
        destination_label="Denver, CO",
        origin_lat=41.8781,
        origin_lon=-87.6298,
        destination_lat=39.7392,
        destination_lon=-104.9903,
        departure_utc=now + timedelta(hours=2),
        load_weight_lb=42_000,
        status=RouteAnalysis.Status.COMPLETED,
        risk_policy_version="2026-11-a",
    )


def _login(client: APIClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/token/",
        {"username": username, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    return response.json()["access"]


def test_register_returns_tokens_and_user_profile():
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"username": "driver", "password": PASSWORD, "email": "driver@example.com"},
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["access"]
    assert payload["refresh"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {payload['access']}")
    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.json() == {
        "authenticated": True,
        "id": User.objects.get(username="driver").id,
        "username": "driver",
        "email": "driver@example.com",
    }


def test_duplicate_username_is_rejected_with_field_error():
    User.objects.create_user(username="driver", password=PASSWORD)
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/",
        {"username": "driver", "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid"
    assert "username" in response.json()["errors"]


def test_login_and_anonymous_profile():
    User.objects.create_user(username="driver", password=PASSWORD)
    client = APIClient()

    anonymous = client.get("/api/v1/auth/me/")
    assert anonymous.json() == {"authenticated": False}

    access = _login(client, "driver")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    me = client.get("/api/v1/auth/me/")
    assert me.json()["authenticated"] is True
    assert me.json()["username"] == "driver"


def test_history_is_scoped_to_the_signed_in_user():
    owner = User.objects.create_user(username="owner", password=PASSWORD)
    other = User.objects.create_user(username="other", password=PASSWORD)
    owned = _analysis(owner=owner)
    anonymous = _analysis(owner=None)
    other_analysis = _analysis(owner=other)

    client = APIClient()
    anonymous_ids = {item["id"] for item in client.get("/api/v1/analyses/").json()["results"]}
    assert anonymous_ids == {str(anonymous.id)}

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {_login(client, 'owner')}")
    owner_ids = {item["id"] for item in client.get("/api/v1/analyses/").json()["results"]}
    assert owner_ids == {str(owned.id), str(anonymous.id)}
    assert str(other_analysis.id) not in owner_ids


def test_private_analysis_detail_and_delete_are_hidden_from_others():
    owner = User.objects.create_user(username="owner", password=PASSWORD)
    User.objects.create_user(username="other", password=PASSWORD)
    owned = _analysis(owner=owner)

    anonymous_client = APIClient()
    assert anonymous_client.get(f"/api/v1/analyses/{owned.id}/").status_code == 404
    assert anonymous_client.delete(f"/api/v1/analyses/{owned.id}/").status_code == 404

    other_client = APIClient()
    other_client.credentials(HTTP_AUTHORIZATION=f"Bearer {_login(other_client, 'other')}")
    assert other_client.get(f"/api/v1/analyses/{owned.id}/").status_code == 404

    owner_client = APIClient()
    owner_client.credentials(HTTP_AUTHORIZATION=f"Bearer {_login(owner_client, 'owner')}")
    assert owner_client.get(f"/api/v1/analyses/{owned.id}/").status_code == 200
    assert owner_client.delete(f"/api/v1/analyses/{owned.id}/").status_code == 204
