from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class RouteAnalysis(models.Model):
    """Immutable request plus the aggregated outcome of one analysis run."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="route_analyses",
        help_text="User who requested the analysis, if authenticated.",
    )

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        ROUTING = "routing", "Routing"
        WEATHER = "weather", "Weather"
        SCORING = "scoring", "Scoring"
        COMPLETED = "completed", "Completed"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    origin_query = models.CharField(max_length=255)
    destination_query = models.CharField(max_length=255)
    origin_label = models.CharField(max_length=500)
    destination_label = models.CharField(max_length=500)
    origin_lat = models.FloatField()
    origin_lon = models.FloatField()
    destination_lat = models.FloatField()
    destination_lon = models.FloatField()
    origin_timezone = models.CharField(max_length=64, default="UTC")
    destination_timezone = models.CharField(max_length=64, default="UTC")

    departure_utc = models.DateTimeField()
    load_weight_lb = models.PositiveIntegerField()
    spacing_miles = models.PositiveSmallIntegerField(default=25)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    travel_advisory = models.CharField(max_length=32, default="unknown")
    recommended_route = models.ForeignKey(
        "RouteOption",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recommended_for",
    )
    providers = models.JSONField(default=dict, blank=True)
    limitations = models.JSONField(default=list, blank=True)
    error = models.JSONField(default=dict, blank=True)
    risk_policy_version = models.CharField(max_length=32, default="unknown")
    request_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.origin_query} → {self.destination_query} ({self.status})"


class RouteOption(models.Model):
    analysis = models.ForeignKey(RouteAnalysis, on_delete=models.CASCADE, related_name="routes")
    sequence = models.PositiveSmallIntegerField()
    rank = models.PositiveSmallIntegerField(default=0)
    recommended = models.BooleanField(default=False)
    disqualified = models.BooleanField(default=False)

    distance_miles = models.FloatField()
    duration_seconds = models.FloatField()
    eta_utc = models.DateTimeField()
    geometry = models.JSONField()
    metrics = models.JSONField(default=dict)
    hourly_risk = models.JSONField(default=dict)
    provider = models.CharField(max_length=32, default="valhalla")
    costing = models.CharField(max_length=32, default="truck")
    provider_route_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["analysis", "sequence"], name="unique_route_sequence_per_analysis"
            )
        ]

    def __str__(self) -> str:
        return f"Route {self.sequence + 1} ({self.distance_miles:.0f} mi)"


class Checkpoint(models.Model):
    route = models.ForeignKey(RouteOption, on_delete=models.CASCADE, related_name="checkpoints")
    spacing_miles = models.PositiveSmallIntegerField()
    sequence = models.PositiveIntegerField()
    cumulative_miles = models.FloatField()
    lat = models.FloatField()
    lon = models.FloatField()
    eta_utc = models.DateTimeField()
    timezone = models.CharField(max_length=64, default="UTC")

    weather = models.JSONField(default=dict)
    weather_status = models.CharField(max_length=16, default="ok")
    base_risk = models.PositiveSmallIntegerField(default=1)
    risk = models.PositiveSmallIntegerField(default=1)
    risk_label = models.CharField(max_length=16, default="Low")
    reasons = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["spacing_miles", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["route", "spacing_miles", "sequence"],
                name="unique_checkpoint_per_spacing",
            )
        ]
        indexes = [models.Index(fields=["route", "spacing_miles", "sequence"])]

    def __str__(self) -> str:
        return f"{self.spacing_miles} mi #{self.sequence} @ {self.risk_label}"


class AnalysisEvent(models.Model):
    analysis = models.ForeignKey(RouteAnalysis, on_delete=models.CASCADE, related_name="events")
    created_at = models.DateTimeField(auto_now_add=True)
    stage = models.CharField(max_length=32)
    level = models.CharField(max_length=16, default="info")
    message = models.CharField(max_length=500)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.stage}: {self.message}"
