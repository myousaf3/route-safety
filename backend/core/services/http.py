"""HTTP helpers: retries, timeouts, and a shared session."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_session_lock = threading.Lock()
_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                session = requests.Session()
                retry = Retry(
                    total=3,
                    connect=3,
                    read=3,
                    status=3,
                    backoff_factor=0.6,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset({"GET", "POST"}),
                    respect_retry_after_header=True,
                    raise_on_status=False,
                )
                adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=32)
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                session.headers.update(
                    {
                        "User-Agent": settings.PROVIDER_USER_AGENT,
                        "Accept": "application/json",
                    }
                )
                _session = session
    return _session


class ProviderError(Exception):
    """Raised when an upstream provider cannot fulfil a request."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


def request_json(
    method: str,
    url: str,
    *,
    provider: str,
    timeout: float | None = None,
    **kwargs: Any,
) -> Any:
    started = time.perf_counter()
    try:
        response = get_session().request(
            method, url, timeout=timeout or settings.HTTP_TIMEOUT_SECONDS, **kwargs
        )
    except requests.Timeout as exc:
        logger.warning(
            "provider_timeout", extra={"provider": provider, "url": url, "error_code": "timeout"}
        )
        raise ProviderError(provider, "Provider timed out", retryable=True) from exc
    except requests.RequestException as exc:
        logger.warning(
            "provider_request_failed",
            extra={"provider": provider, "url": url, "error_code": type(exc).__name__},
        )
        raise ProviderError(provider, "Provider request failed", retryable=True) from exc

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "provider_request",
        extra={
            "provider": provider,
            "latency_ms": latency_ms,
            "status_code": response.status_code,
        },
    )

    if response.status_code == 429:
        raise ProviderError(
            provider, "Provider rate limit reached", status_code=429, retryable=True
        )
    if response.status_code >= 500:
        raise ProviderError(
            provider,
            "Provider is temporarily unavailable",
            status_code=response.status_code,
            retryable=True,
        )
    if response.status_code >= 400:
        raise ProviderError(
            provider,
            f"Provider rejected the request ({response.status_code})",
            status_code=response.status_code,
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(provider, "Provider returned malformed JSON") from exc


def map_bounded(items: list[Any], fn: Callable[[Any], Any], *, concurrency: int = 6) -> list[Any]:
    """Bounded parallel map using threads (call sites are already worker-context)."""

    from concurrent.futures import ThreadPoolExecutor

    if not items:
        return []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        return list(executor.map(fn, items))
