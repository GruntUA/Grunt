"""Standard API response wrappers."""

from __future__ import annotations

from math import ceil
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class StandardResponse[T](BaseModel):
    success: bool = True
    data: T


class StandardListResponse[T](BaseModel):
    success: bool = True
    data: list[T]
    meta: PaginationMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[str] = []


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


# ── Response helpers ──────────────────────────────────────────────────────────

_MISSING = object()


def ok(data: Any = _MISSING, **extra: Any) -> dict[str, Any]:
    """Wrap data in a standard success response.

    Usage::

        return ok(doc)           # {"success": True, "data": doc}
        return ok([])            # {"success": True, "data": []}
        return ok()              # {"success": True}
        return ok(message="ok") # {"success": True, "message": "ok"}
    """
    result: dict[str, Any] = {"success": True}
    if data is not _MISSING:
        result["data"] = data
    result.update(extra)
    return result


def ok_list(
    items: list[Any],
    *,
    total: int,
    page: int = 1,
    per_page: int = 20,
    **extra: Any,
) -> dict[str, Any]:
    """Wrap a list in a standard paginated response.

    Usage::

        return ok_list(docs, total=total, page=page, per_page=per_page)
    """
    pages = ceil(total / per_page) if per_page else 1
    return {
        "success": True,
        "data": items,
        "meta": {"total": total, "page": page, "per_page": per_page, "pages": pages},
        **extra,
    }
