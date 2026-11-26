"""API views: analyses, place search, policy, health, metrics, OpenAPI."""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db import connection
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from drf_spectacular.views import SpectacularAPIView
from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.errors import ProblemError
from core.middleware import render_metrics
from core.models import RouteAnalysis
from core.payloads import analysis_detail_payload
from core.serializers import AnalysisRequestSerializer, HistoryItemSerializer
from core.services.analysis import (
    SPACINGS,
    _validate_departure,
    create_queued_analysis,
)
from core.services.geocoding import search_places
from core.services.http import ProviderError
from core.services.risk import RISK_LABELS, RiskLevel
from core.tasks import process_analysis_task

logger = logging.getLogger(__name__)


class AnalysisCreateThrottle(ScopedRateThrottle):
    scope = "analysis"


class AnalysisListCreateView(APIView):
    @extend_schema(
        summary="List saved analyses",
        parameters=[
            OpenApiParameter("status", str, description="Filter by analysis status"),
            OpenApiParameter("cursor", str, description="Cursor pagination token"),
            OpenApiParameter("page_size", int, description="Page size (max 50)"),
        ],
        responses={200: OpenApiTypes.OBJECT},
        tags=["analyses"],
    )
    def get(self, request):
        queryset = (
            RouteAnalysis.objects.select_related("recommended_route")
            .annotate(route_count=Count("routes"))
            .all()
        )
        if request.user.is_authenticated:
            queryset = queryset.filter(owner__in=[request.user, None])
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in RouteAnalysis.Status.values:
                raise ProblemError(
                    code="invalid_status_filter",
                    title="Invalid status filter",
                    detail=f"status must be one of: {', '.join(RouteAnalysis.Status.values)}",
                    status_code=400,
                )
            queryset = queryset.filter(status=status_filter)

        paginator = CursorPagination()
        paginator.page_size = 10
        paginator.max_page_size = 50
        paginator.page_size_query_param = "page_size"
        paginator.ordering = "-created_at"
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = HistoryItemSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary="Create and run a route safety analysis",
        request=AnalysisRequestSerializer,
        responses={
            201: OpenApiResponse(description="Completed analysis with routes and checkpoints"),
            400: OpenApiTypes.OBJECT,
            422: OpenApiTypes.OBJECT,
            502: OpenApiTypes.OBJECT,
        },
        tags=["analyses"],
    )
    def post(self, request):
        serializer = AnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        _validate_departure(data["departure"])
        analysis = create_queued_analysis(
            origin_query=data["origin"],
            destination_query=data["destination"],
            departure_utc=data["departure"],
            load_weight_lb=data["load_weight_lb"],
            spacing_miles=data.get("spacing_miles", 25),
            owner=request.user if request.user.is_authenticated else None,
        )
        process_analysis_task.delay(str(analysis.id))

        analysis = (
            RouteAnalysis.objects.select_related("recommended_route")
            .prefetch_related("routes__checkpoints")
            .get(pk=analysis.id)
        )
        payload = analysis_detail_payload(analysis)
        response = Response(payload, status=status.HTTP_202_ACCEPTED)
        response["Location"] = f"/api/v1/analyses/{analysis.id}/"
        return response

    def get_throttles(self):
        if self.request.method == "POST":
            return [AnalysisCreateThrottle()]
        return super().get_throttles()


class AnalysisDetailView(APIView):
    @extend_schema(
        summary="Get a saved analysis",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        tags=["analyses"],
    )
    def get(self, request, pk):
        analysis = get_object_or_404(
            RouteAnalysis.objects.select_related("recommended_route").prefetch_related(
                "routes__checkpoints"
            ),
            pk=pk,
        )
        return Response(analysis_detail_payload(analysis))

    @extend_schema(
        summary="Delete a saved analysis",
        responses={204: None, 404: OpenApiTypes.OBJECT},
        tags=["analyses"],
    )
    def delete(self, request, pk):
        analysis = get_object_or_404(RouteAnalysis, pk=pk)
        analysis.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlaceSearchView(APIView):
    throttle_scope = "places"

    @extend_schema(
        summary="Autocomplete place search",
        parameters=[OpenApiParameter("q", str, required=True)],
        responses={200: OpenApiTypes.OBJECT, 502: OpenApiTypes.OBJECT},
        tags=["places"],
    )
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 3:
            return Response({"results": []})
        try:
            places = search_places(query, limit=5)
        except ProviderError as exc:
            raise ProblemError(
                code="geocoding_unavailable",
                title="Geocoding provider unavailable",
                detail="Could not reach the location service. Please retry.",
                status_code=502,
            ) from exc
        return Response(
            {
                "results": [
                    {
                        "label": place.label,
                        "lat": place.lat,
                        "lon": place.lon,
                        "timezone": place.timezone,
                    }
                    for place in places
                ]
            }
        )


class RiskPolicyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Risk policy thresholds, load rules, and ranking key",
        responses={200: OpenApiTypes.OBJECT},
        tags=["policy"],
    )
    def get(self, request):
        return Response(
            {
                "version": "2026-11-a",
                "levels": [
                    {"value": int(level), "label": RISK_LABELS[level]} for level in RiskLevel
                ],
                "thresholds": {
                    "wind_mph": {
                        "low": "<25",
                        "moderate": "25-34.99",
                        "high": "35-44.99",
                        "severe": "45-54.99",
                        "no_travel": ">=55",
                    },
                    "rain_in_hr": {
                        "low": "<0.10",
                        "moderate": "0.10-0.249",
                        "high": "0.25-0.499",
                        "severe": "0.50-1.00",
                        "no_travel": ">1.00",
                    },
                    "snow_in_hr": {
                        "low": "<0.5",
                        "moderate": "0.5-0.99",
                        "high": "1.0-1.99",
                        "severe": "2.0-3.00",
                        "no_travel": ">3.00",
                    },
                },
                "load_rules": [
                    "Wind >= 55 mph is No Travel for any load.",
                    "Wind 45-54 mph with a load > 30,000 lb is No Travel.",
                    "Wind 35-44 mph with a load > 40,000 lb is Severe.",
                ],
                "base_risk": "Worst of wind, rain, and snow; load overrides applied afterwards.",
                "ranking_key": [
                    "no_travel_miles",
                    "severe_miles",
                    "high_miles",
                    "average_risk_score",
                    "duration_seconds",
                ],
                "spacings_miles": list(SPACINGS),
                "heatmap_hours": 48,
                "missing_weather": "Unknown; never treated as zero and never treated as safe.",
            }
        )


class OpenAPISchemaView(SpectacularAPIView):
    permission_classes = [AllowAny]
    throttle_classes = []


class HealthLiveView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        return Response({"status": "ok", "service": "route-safety-api"})


class HealthReadyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        checks: dict[str, str] = {}
        ready = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            ready = False
        try:
            cache.set("health:ready", "ok", timeout=10)
            checks["cache"] = "ok" if cache.get("health:ready") == "ok" else "error"
            ready = ready and checks["cache"] == "ok"
        except Exception:
            checks["cache"] = "error"
            ready = False
        return Response(
            {"status": "ready" if ready else "not_ready", "checks": checks},
            status=200 if ready else 503,
        )


class MetricsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        return HttpResponse(render_metrics(), content_type="text/plain; version=0.0.4")
