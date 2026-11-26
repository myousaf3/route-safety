"""Project URL routes for API v1."""

from __future__ import annotations

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core import auth, views

urlpatterns = [
    path("analyses/", views.AnalysisListCreateView.as_view(), name="analysis-list"),
    path("analyses/<uuid:pk>/", views.AnalysisDetailView.as_view(), name="analysis-detail"),
    path("places/", views.PlaceSearchView.as_view(), name="place-search"),
    path("policy/", views.RiskPolicyView.as_view(), name="risk-policy"),
    path("openapi/", views.OpenAPISchemaView.as_view(), name="openapi-schema"),
    path("auth/register/", auth.RegisterView.as_view(), name="auth-register"),
    path("auth/token/", TokenObtainPairView.as_view(), name="auth-token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/me/", auth.MeView.as_view(), name="auth-me"),
]
