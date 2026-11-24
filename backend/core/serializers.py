from __future__ import annotations

from rest_framework import serializers

from core.models import RouteAnalysis


class AnalysisRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(min_length=3, max_length=255, trim_whitespace=True)
    destination = serializers.CharField(min_length=3, max_length=255, trim_whitespace=True)
    departure = serializers.DateTimeField(
        help_text="ISO 8601 departure timestamp; include an offset when possible."
    )
    load_weight_lb = serializers.IntegerField(min_value=1_000, max_value=120_000)
    spacing_miles = serializers.ChoiceField(choices=[10, 25, 50], default=25, required=False)

    def validate(self, attrs):
        if attrs["origin"].strip().lower() == attrs["destination"].strip().lower():
            raise serializers.ValidationError(
                {"destination": "Origin and destination must be different."}
            )
        return attrs


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    timezone = serializers.CharField()


class HistoryItemSerializer(serializers.ModelSerializer):
    origin = serializers.CharField(source="origin_label")
    destination = serializers.CharField(source="destination_label")
    route_count = serializers.IntegerField(read_only=True)
    recommended_route_id = serializers.IntegerField(read_only=True)
    summary_metrics = serializers.SerializerMethodField()

    class Meta:
        model = RouteAnalysis
        fields = [
            "id",
            "created_at",
            "status",
            "travel_advisory",
            "origin",
            "destination",
            "departure_utc",
            "load_weight_lb",
            "spacing_miles",
            "route_count",
            "recommended_route_id",
            "summary_metrics",
        ]

    def get_summary_metrics(self, obj: RouteAnalysis) -> dict | None:
        route = obj.recommended_route
        if route is None:
            return None
        return {
            "distance_miles": route.distance_miles,
            "duration_seconds": route.duration_seconds,
            "severe_miles": route.metrics.get("severe_miles", 0),
            "high_miles": route.metrics.get("high_miles", 0),
            "average_risk_score": route.metrics.get("average_risk_score", 0),
        }
