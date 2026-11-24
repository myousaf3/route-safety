"""Load the deterministic demo analysis shipped with the repository.

The snapshot was captured from a live provider run so the walkthrough works even
when Valhalla, Nominatim, or Open-Meteo are unavailable. It is labelled as demo
data in the analysis limitations and is safe to run repeatedly.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import Checkpoint, RouteAnalysis, RouteOption

DEMO_FINGERPRINT = "demo-seed-v1"
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "demo_analysis.json"


class Command(BaseCommand):
    help = "Seed a deterministic demo analysis for walkthroughs and offline demos."

    def handle(self, *args, **options):
        if not FIXTURE_PATH.exists():
            raise CommandError(f"Demo fixture not found: {FIXTURE_PATH}")

        payload = json.loads(FIXTURE_PATH.read_text())
        request = payload["request"]
        origin = request["origin"]
        destination = request["destination"]
        departure = parse_datetime(request["departure_utc"])
        if departure is None:
            raise CommandError("Demo fixture has an invalid departure timestamp.")
        if timezone.is_naive(departure):
            departure = timezone.make_aware(departure)

        with transaction.atomic():
            RouteAnalysis.objects.filter(request_fingerprint=DEMO_FINGERPRINT).delete()

            analysis = RouteAnalysis.objects.create(
                origin_query=origin["query"],
                destination_query=destination["query"],
                origin_label=origin["label"],
                destination_label=destination["label"],
                origin_lat=origin["lat"],
                origin_lon=origin["lon"],
                destination_lat=destination["lat"],
                destination_lon=destination["lon"],
                origin_timezone=origin["timezone"],
                destination_timezone=destination["timezone"],
                departure_utc=departure,
                load_weight_lb=request["load_weight_lb"],
                spacing_miles=request["spacing_miles"],
                status=payload["status"],
                travel_advisory=payload["travel_advisory"],
                providers=payload["providers"],
                limitations=[
                    *payload.get("limitations", []),
                    "Seeded demo snapshot captured from a live provider run; "
                    "forecasts and traffic have changed since capture.",
                ],
                risk_policy_version=payload["risk_policy_version"],
                request_fingerprint=DEMO_FINGERPRINT,
            )

            recommended_id: int | None = None
            for route_data in payload["routes"]:
                route = RouteOption.objects.create(
                    analysis=analysis,
                    sequence=route_data["sequence"],
                    rank=route_data["rank"],
                    recommended=route_data["recommended"],
                    disqualified=route_data["disqualified"],
                    distance_miles=route_data["distance_miles"],
                    duration_seconds=route_data["duration_seconds"],
                    eta_utc=parse_datetime(route_data["eta_utc"]),
                    geometry=route_data["geometry"],
                    metrics=route_data["metrics"],
                    hourly_risk=route_data["heatmap"],
                    provider=route_data["provider"],
                    costing=route_data["costing"],
                    provider_route_index=route_data["sequence"],
                )
                if route_data["recommended"]:
                    recommended_id = route.id

                checkpoints = []
                for spacing, rows in route_data["checkpoints"].items():
                    for row in rows:
                        checkpoints.append(
                            Checkpoint(
                                route=route,
                                spacing_miles=int(spacing),
                                sequence=row["sequence"],
                                cumulative_miles=row["cumulative_miles"],
                                lat=row["lat"],
                                lon=row["lon"],
                                eta_utc=parse_datetime(row["eta_utc"]),
                                timezone=row["timezone"],
                                weather=row["weather"],
                                weather_status=row["weather_status"],
                                base_risk=row["base_risk"],
                                risk=row["risk"],
                                risk_label=row["risk_label"],
                                reasons=row["reasons"],
                            )
                        )
                Checkpoint.objects.bulk_create(checkpoints)

            analysis.recommended_route_id = recommended_id
            analysis.save(update_fields=["recommended_route"])
            # Make the demo the most recent history entry without changing the snapshot data.
            RouteAnalysis.objects.filter(pk=analysis.pk).update(created_at=timezone.now())

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded demo analysis {analysis.id} "
                f"({origin['query']} → {destination['query']}) with "
                f"{len(payload['routes'])} routes."
            )
        )
