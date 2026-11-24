"""RFC 9457-style problem details for API errors."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.services.http import ProviderError


class ProblemError(Exception):
    def __init__(
        self,
        *,
        code: str,
        title: str,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        errors: Any = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.title = title
        self.detail = detail
        self.status_code = status_code
        self.errors = errors


def problem_response(
    *,
    request,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: Any = None,
) -> Response:
    payload: dict[str, Any] = {
        "type": f"https://spotter.example/problems/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "instance": request.path if request is not None else None,
    }
    correlation_id = getattr(request, "correlation_id", None)
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if errors is not None:
        payload["errors"] = errors
    response = Response(payload, status=status_code, content_type="application/problem+json")
    return response


def problem_details_exception_handler(exc, context):
    request = context.get("request")
    if isinstance(exc, ProblemError):
        return problem_response(
            request=request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
        )

    if isinstance(exc, ProviderError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if exc.status_code == 429 else 502
        return problem_response(
            request=request,
            status_code=status_code,
            code="provider_unavailable",
            title="Weather or routing provider unavailable",
            detail="An upstream provider could not complete the analysis. Please retry shortly.",
        )

    if isinstance(exc, APIException):
        code = getattr(exc, "default_code", "api_error") or "api_error"
        detail = exc.detail
        if isinstance(detail, dict | list):
            return problem_response(
                request=request,
                status_code=exc.status_code,
                code=code,
                title="Request validation failed",
                detail="One or more fields are invalid.",
                errors=detail,
            )
        return problem_response(
            request=request,
            status_code=exc.status_code,
            code=code,
            title="Request failed",
            detail=str(detail),
        )

    # Let DRF/Django handle unexpected exceptions (500) while keeping the standard shape if seen.
    response = exception_handler(exc, context)
    if response is not None:
        return response
    return None
