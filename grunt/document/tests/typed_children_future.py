"""A controller module with ``from __future__ import annotations`` - its
annotations are strings (test_typed_children)."""

from __future__ import annotations

from grunt.document.base import Document


class FutLine(Document):
    qty: int | None = None


class FutOrder(Document):
    lines: list[FutLine] = []
    named: list[FutNamed] = []  # noqa: F821  # pyright: ignore[reportUndefinedVariable]
    notes: list[dict] = []
