"""Open-Meteo forecast adapter: batched hourly series with caching."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache

from core.services.http import ProviderError, map_bounded, request_json

logger = logging.getLogger(__name__)

VARIABLES = [
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "temperature_2m",
    "visibility",
    "weather_code",
]


@dataclass
class WeatherSample:
    at_utc: datetime
    wind_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None
    temperature_f: float | None
    visibility_miles: float | None
    weather_code: int | None
    wind_gust_mph: float | None = None

    @property
    def status(self) -> str:
        if self.wind_mph is None and self.rain_in_hr is None and self.snow_in_hr is None:
            return "unknown"
        return "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "wind_mph": _round(self.wind_mph, 1),
            "wind_gust_mph": _round(self.wind_gust_mph, 1),
            "rain_in_hr": _round(self.rain_in_hr, 3),
            "snow_in_hr": _round(self.snow_in_hr, 3),
            "temperature_f": _round(self.temperature_f, 1),
            "visibility_miles": _round(self.visibility_miles, 2),
            "weather_code": self.weather_code,
            "forecast_time_utc": self.at_utc.isoformat(),
        }


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


@dataclass
class WeatherSeries:
    latitude: float
    longitude: float
    times: list[datetime]
    wind: list[float | None]
    wind_gust: list[float | None]
    rain: list[float | None]
    snow: list[float | None]
    temperature: list[float | None]
    visibility: list[float | None]
    weather_code: list[int | None]

    def sample(self, when: datetime) -> WeatherSample:
        if not self.times:
            return WeatherSample(
                at_utc=when,
                wind_mph=None,
                rain_in_hr=None,
                snow_in_hr=None,
                temperature_f=None,
                visibility_miles=None,
                weather_code=None,
            )
        # Forecast is hourly; choose the closest hour and require it to be within 45 minutes.
        index = min(
            range(len(self.times)),
            key=lambda i: abs((self.times[i] - when).total_seconds()),
        )
        if abs((self.times[index] - when).total_seconds()) > 45 * 60:
            return WeatherSample(
                at_utc=when,
                wind_mph=None,
                rain_in_hr=None,
                snow_in_hr=None,
                temperature_f=None,
                visibility_miles=None,
                weather_code=None,
            )
        return WeatherSample(
            at_utc=self.times[index],
            wind_mph=self.wind[index],
            rain_in_hr=self.rain[index],
            snow_in_hr=self.snow[index],
            temperature_f=self.temperature[index],
            visibility_miles=self.visibility[index],
            weather_code=self.weather_code[index],
            wind_gust_mph=self.wind_gust[index],
        )


def _num(values: list[Any] | None, index: int) -> float | None:
    if not values or index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_hour(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _series_from_payload(
    payload: dict[str, Any], latitude: float, longitude: float
) -> WeatherSeries:
    hourly = payload.get("hourly") or {}
    raw_times = hourly.get("time") or []
    times = [_parse_hour(value) for value in raw_times]
    size = len(times)

    def column(name: str) -> list[float | None]:
        values = hourly.get(name) or []
        return [_num(values, index) for index in range(size)]

    rain_values = column("rain")
    shower_values = column("showers")
    rain = [
        (rain_values[i] or 0.0) + (shower_values[i] or 0.0)
        if rain_values[i] is not None or shower_values[i] is not None
        else None
        for i in range(size)
    ]
    # Open-Meteo reports snowfall in centimetres. Convert to inches/hour.
    snow_cm = column("snowfall")
    snow = [None if value is None else value / 2.54 for value in snow_cm]
    visibility_m = column("visibility")
    visibility_miles = [None if value is None else value / 1609.344 for value in visibility_m]

    return WeatherSeries(
        latitude=latitude,
        longitude=longitude,
        times=times,
        wind=column("wind_speed_10m"),
        wind_gust=column("wind_gusts_10m"),
        rain=rain,
        snow=snow,
        temperature=column("temperature_2m"),
        visibility=visibility_miles,
        weather_code=[None if v is None else int(v) for v in column("weather_code")],
    )


def _cache_key(points: list[tuple[float, float]], start: datetime, end: datetime) -> str:
    digest = hashlib.sha256(
        (
            "|".join(f"{lat:.3f},{lon:.3f}" for lat, lon in points)
            + start.date().isoformat()
            + end.date().isoformat()
        ).encode()
    ).hexdigest()[:32]
    return f"weather:batch:{digest}"


def fetch_weather_series(
    points: list[tuple[float, float]], start: datetime, end: datetime
) -> list[WeatherSeries]:
    """Fetch hourly series for each (lat, lon), deduplicated and cached."""

    cache_key = _cache_key(points, start, end)
    cached = cache.get(cache_key)
    if cached is not None:
        return [
            _series_from_payload(item["payload"], item["latitude"], item["longitude"])
            for item in cached
        ]

    # Open-Meteo forecast range: today through 16 days. Clamp the requested window.
    today = datetime.now(UTC).date()
    start_date = max(start.date(), today - timedelta(days=1))
    end_date = min(end.date() + timedelta(days=1), today + timedelta(days=15))
    if end_date < start_date:
        end_date = start_date

    chunks = [
        points[index : index + settings.OPEN_METEO_BATCH_SIZE]
        for index in range(0, len(points), settings.OPEN_METEO_BATCH_SIZE)
    ]

    def fetch_chunk(chunk: list[tuple[float, float]]) -> list[WeatherSeries]:
        params = {
            "latitude": ",".join(f"{lat:.5f}" for lat, _ in chunk),
            "longitude": ",".join(f"{lon:.5f}" for _, lon in chunk),
            "hourly": ",".join(VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "temperature_unit": "fahrenheit",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "timezone": "UTC",
        }
        data = request_json(
            "GET",
            f"{settings.OPEN_METEO_BASE_URL}/v1/forecast",
            provider="open-meteo",
            params=params,
        )
        payloads = data if isinstance(data, list) else [data]
        if len(payloads) != len(chunk):
            raise ProviderError("open-meteo", "Weather provider returned an unexpected payload")
        result: list[WeatherSeries] = []
        for (lat, lon), payload in zip(chunk, payloads, strict=False):
            if not isinstance(payload, dict) or payload.get("error"):
                raise ProviderError("open-meteo", "Weather provider returned an error")
            result.append(_series_from_payload(payload, lat, lon))
        return result

    results = map_bounded(chunks, fetch_chunk, concurrency=settings.WEATHER_FETCH_CONCURRENCY)
    series = [item for chunk in results for item in chunk]

    cache.set(
        cache_key,
        [
            {
                "latitude": item.latitude,
                "longitude": item.longitude,
                "payload": {
                    "hourly": {
                        "time": [time.isoformat() for time in item.times],
                        "wind_speed_10m": item.wind,
                        "wind_gusts_10m": item.wind_gust,
                        "rain": item.rain,
                        "snowfall": [None if v is None else v * 2.54 for v in item.snow],
                        "temperature_2m": item.temperature,
                        "visibility": [
                            None if v is None else v * 1609.344 for v in item.visibility
                        ],
                        "weather_code": item.weather_code,
                    }
                },
            }
            for item in series
        ],
        timeout=60 * 20,
    )
    return series


class WeatherIndex:
    """Lookup series by rounded coordinate for checkpoint assignment."""

    def __init__(self, series: list[WeatherSeries], coordinates: list[tuple[float, float]]):
        self._series = series
        self._by_coordinate = {
            self.key(lat, lon): series_item
            for (lat, lon), series_item in zip(coordinates, series, strict=False)
        }

    @staticmethod
    def key(lat: float, lon: float) -> str:
        return f"{lat:.5f},{lon:.5f}"

    def sample(self, lat: float, lon: float, when: datetime) -> WeatherSample:
        series = self._by_coordinate.get(self.key(lat, lon))
        if series is None:
            return WeatherSample(
                at_utc=when,
                wind_mph=None,
                rain_in_hr=None,
                snow_in_hr=None,
                temperature_f=None,
                visibility_miles=None,
                weather_code=None,
            )
        return series.sample(when)
