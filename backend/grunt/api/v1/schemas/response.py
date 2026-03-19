"""Standard API response wrappers."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T


class StandardListResponse(BaseModel, Generic[T]):
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
