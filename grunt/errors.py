"""Grunt error types and HTTP error helpers.

Two layers live here:

* :class:`GruntError` — a user-facing domain error raised via ``grunt.throw()``
  inside controllers/hooks; mapped to an HTTP status by the global handler.
* :class:`APIError` (+ factory helpers like :func:`forbidden`) — HTTP errors with
  a *semantic* error code and structured details, plus :func:`error_body`, the
  single builder for the JSON error envelope used by every error response.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from grunt.i18n import _


class GruntError(Exception):
    """User-facing error raised via ``grunt.throw()``.

    Caught by the document pipeline and returned as an HTTP 422 response.
    """

    def __init__(self, message: str, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


def error_body(
    code: str,
    message: str,
    details: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical JSON error envelope returned by every error response."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        },
    }


class APIError(HTTPException):
    """An :class:`HTTPException` carrying a semantic error code + structured details.

    The global exception handler renders these into :func:`error_body`. Prefer the
    factory helpers below over constructing this directly.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.details = details or []


def forbidden(message: str | None = None, *, details: list[Any] | None = None) -> APIError:
    """403 — the user is authenticated but lacks permission."""
    return APIError(403, "FORBIDDEN", message or _("Not permitted"), details=details)


def not_found(message: str | None = None, *, details: list[Any] | None = None) -> APIError:
    """404 — the requested resource does not exist."""
    return APIError(404, "NOT_FOUND", message or _("Not found"), details=details)


def conflict(message: str, *, details: list[Any] | None = None) -> APIError:
    """409 — the request conflicts with the current state (duplicate, etc.)."""
    return APIError(409, "CONFLICT", message, details=details)


def unprocessable(message: str, *, details: list[Any] | None = None) -> APIError:
    """422 — the request is well-formed but failed validation."""
    return APIError(422, "VALIDATION_ERROR", message, details=details)


def too_many_requests(
    message: str | None = None,
    *,
    details: list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> APIError:
    """429 — rate limit exceeded."""
    return APIError(
        429,
        "RATE_LIMIT_EXCEEDED",
        message or _("Too many requests. Try again later."),
        details=details,
        headers=headers,
    )
