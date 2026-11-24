"""Health, metrics, and documentation routes outside the versioned API."""

from __future__ import annotations

from django.urls import path
from drf_spectacular.views import SpectacularSwaggerView

from core.views import HealthLiveView, HealthReadyView, MetricsView

urlpatterns = [
    path("health/live", HealthLiveView.as_view(), name="health-live"),
    path("health/ready", HealthReadyView.as_view(), name="health-ready"),
    path("metrics", MetricsView.as_view(), name="metrics"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="openapi-schema"),
        name="swagger-ui",
    ),
]
