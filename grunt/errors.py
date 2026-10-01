"""Grunt error types and HTTP error helpers.

Two layers live here:

* :class:`ApplicationError` — a user-facing domain error raised via
  ``grunt.throw()``; its ``code`` picks the HTTP status (:data:`APPLICATION_ERROR_STATUS`).
* :class:`APIError` (+ factory helpers like :func:`forbidden`) — HTTP errors with
  a *semantic* error code and structured details, plus :func:`error_body`, the
  single builder for the JSON error envelope used by every error response.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from grunt.i18n import _

# ``grunt.throw(..., code=...)`` → HTTP status; anything else is a 422.
APPLICATION_ERROR_STATUS: dict[str, int] = {
    "UNAUTHORIZED": 401,
    "PERMISSION_DENIED": 403,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "DUPLICATE_DATA": 409,
    "VALIDATION_ERROR": 422,
    "RATE_LIMITED": 429,
}


class ApplicationError(Exception):
    """User-facing error raised by ``grunt.throw()``."""

    def __init__(self, message: str, code: str = "ERROR", title: str = "") -> None:
        self.message = message
        self.code = code
        self.title = title
        super().__init__(message)

    @property
    def status_code(self) -> int:
        return APPLICATION_ERROR_STATUS.get(self.code, 422)

    def to_api_error(self) -> APIError:
        """The same error as an HTTP exception — for code paths that only speak HTTP."""
        return APIError(self.status_code, self.code, self.message)


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
