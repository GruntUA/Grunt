"""Explicit response serialization for ``Document`` controllers.

No magic — a ``Schema`` subclass just names the fields to expose, then
``.dump()``/``.dump_many()`` are called explicitly at the point a whitelisted
method builds its response::

    class UserPublic(Schema):
        fields = ("name", "email", "full_name", "roles")

    @grunt.whitelist()
    async def whoami() -> dict:
        return UserPublic.dump(grunt.current_user())
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterable

    from grunt.document.base import Document


class Schema:
    """Declares which fields of a ``Document`` are exposed in an API response."""

    fields: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def dump(cls, doc: Document) -> dict[str, Any]:
        return {f: getattr(doc, f) for f in cls.fields}

    @classmethod
    def dump_many(cls, docs: Iterable[Document]) -> list[dict[str, Any]]:
        return [cls.dump(d) for d in docs]
