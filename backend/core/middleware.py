"""Correlation IDs, access logs, and lightweight process metrics."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("core.requests")

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_latency_buckets = {"p50": [], "p95": [], "p99": []}
_MAX_LATENCY_SAMPLES = 500


class RequestContextMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
        request.started_at = time.perf_counter()

    def process_response(self, request, response):
        correlation_id = getattr(request, "correlation_id", "")
        elapsed_ms = round(
            (time.perf_counter() - getattr(request, "started_at", time.perf_counter())) * 1000, 1
        )
        response["X-Correlation-ID"] = correlation_id
        response["X-Response-Time-ms"] = str(elapsed_ms)
        response["X-Content-Type-Options"] = "nosniff"

        with _lock:
            _counters[f"http_requests_total|{request.method}|{response.status_code}"] += 1
            if 400 <= response.status_code < 500:
                _counters["http_4xx_total"] += 1
            if response.status_code >= 500:
                _counters["http_5xx_total"] += 1
            _latency_buckets["p50"].append(elapsed_ms)
            if len(_latency_buckets["p50"]) > _MAX_LATENCY_SAMPLES:
                _latency_buckets["p50"].pop(0)

        logger.info(
            "request_complete",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
            },
        )
        return response


def record_analysis(status: str) -> None:
    with _lock:
        _counters[f"analyses_total|{status}"] += 1


def render_metrics() -> str:
    lines: list[str] = []
    with _lock:
        for key, value in sorted(_counters.items()):
            if key.startswith("http_requests_total|"):
                _, method, status_code = key.split("|")
                lines.append(
                    f'http_requests_total{{method="{method}",status="{status_code}"}} {value}'
                )
            else:
                metric = key.split("|")[0]
                labels = key.split("|")[1:]
                if labels:
                    label_text = ",".join(f'label{i}="{label}"' for i, label in enumerate(labels))
                    lines.append(f"{metric}{{{label_text}}} {value}")
                else:
                    lines.append(f"{metric} {value}")
        samples = sorted(_latency_buckets["p50"])
    if samples:

        def percentile(p: float) -> float:
            index = min(len(samples) - 1, max(0, int(round(p * (len(samples) - 1)))))
            return samples[index]

        lines.append(f'http_request_duration_ms{{quantile="0.5"}} {percentile(0.5)}')
        lines.append(f'http_request_duration_ms{{quantile="0.95"}} {percentile(0.95)}')
        lines.append(f'http_request_duration_ms{{quantile="0.99"}} {percentile(0.99)}')
    return "\n".join(lines) + "\n"
