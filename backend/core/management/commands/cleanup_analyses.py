"""Retention cleanup for old analyses and demo data."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import RouteAnalysis


class Command(BaseCommand):
    help = "Delete analyses older than N days (default 30)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--include-demo", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        cutoff = timezone.now() - timedelta(days=days)
        queryset = RouteAnalysis.objects.filter(created_at__lt=cutoff)
        if not options["include_demo"]:
            queryset = queryset.exclude(request_fingerprint__startswith="demo-seed-v1")

        count = queryset.count()
        if options["dry_run"]:
            self.stdout.write(f"Would delete {count} analyses older than {days} days.")
            return

        deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} analyses older than {days} days."))
