from __future__ import annotations

from django.contrib import admin

from core.models import AnalysisEvent, Checkpoint, RouteAnalysis, RouteOption


class RouteOptionInline(admin.TabularInline):
    model = RouteOption
    extra = 0
    readonly_fields = ("distance_miles", "duration_seconds", "rank", "recommended")


@admin.register(RouteAnalysis)
class RouteAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "origin_query",
        "destination_query",
        "status",
        "travel_advisory",
        "created_at",
    )
    list_filter = ("status", "travel_advisory")
    search_fields = ("origin_query", "destination_query", "id")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [RouteOptionInline]


@admin.register(RouteOption)
class RouteOptionAdmin(admin.ModelAdmin):
    list_display = ("analysis", "sequence", "rank", "distance_miles", "recommended")
    list_filter = ("recommended", "disqualified", "provider")


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ("route", "spacing_miles", "sequence", "cumulative_miles", "risk_label")
    list_filter = ("spacing_miles", "risk_label", "weather_status")


@admin.register(AnalysisEvent)
class AnalysisEventAdmin(admin.ModelAdmin):
    list_display = ("analysis", "stage", "level", "created_at")
    list_filter = ("stage", "level")
