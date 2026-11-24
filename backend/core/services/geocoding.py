"""Nominatim geocoding adapter with a polite rate limit and cache."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache

from core.errors import ProblemError
from core.services.geo import timezone_for
from core.services.http import ProviderError, request_json

logger = logging.getLogger(__name__)

_RATE_LOCK = threading.Lock()
_LAST_CALL = 0.0
_MIN_INTERVAL_SECONDS = 1.0


def _throttle() -> None:
    global _LAST_CALL
    with _RATE_LOCK:
        now = time.monotonic()
        wait = _MIN_INTERVAL_SECONDS - (now - _LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float
    timezone: str


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split()).lower()


def search_places(query: str, *, limit: int = 5) -> list[Place]:
    normalized = _normalize_query(query)
    if len(normalized) < 3:
        return []

    digest = hashlib.sha256(f"{normalized}|{limit}".encode()).hexdigest()[:32]
    cache_key = f"geocode:search:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return [Place(**item) for item in cached]

    _throttle()
    try:
        payload: Any = request_json(
            "GET",
            f"{settings.NOMINATIM_BASE_URL}/search",
            provider="nominatim",
            params={
                "q": query.strip(),
                "format": "jsonv2",
                "limit": limit,
                "addressdetails": 1,
                "accept-language": "en",
            },
            headers={"User-Agent": settings.PROVIDER_USER_AGENT},
        )
    except ProviderError:
        raise

    places: list[Place] = []
    if isinstance(payload, list):
        for item in payload:
            try:
                lat = float(item["lat"])
                lon = float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            label = str(item.get("display_name") or item.get("name") or query).strip()
            places.append(
                Place(
                    label=label[:500],
                    lat=lat,
                    lon=lon,
                    timezone=timezone_for(lat, lon),
                )
            )

    cache.set(cache_key, [place.__dict__ for place in places], timeout=60 * 60 * 24)
    return places


def geocode(query: str) -> Place:
    try:
        places = search_places(query, limit=1)
    except ProviderError as exc:
        raise ProblemError(
            code="geocoding_unavailable",
            title="Geocoding provider unavailable",
            detail="Could not reach the location service. Please retry.",
            status_code=502,
        ) from exc

    if not places:
        raise ProblemError(
            code="location_not_found",
            title="Location not found",
            detail=f'We could not find "{query.strip()}". Try a city, state or full address.',
            status_code=422,
        )
    return places[0]
