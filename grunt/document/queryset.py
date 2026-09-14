"""Fluent, typed query builder for :class:`~grunt.document.base.Document` subclasses.

Accessed via ``Document.objects`` (see the ``_ObjectsDescriptor`` on
:class:`~grunt.document.base.Document`). A thin wrapper — every method delegates
to the existing guarded facade (``grunt.get_all``/``grunt.count``/``grunt.new_doc``),
it does not build SQL itself::

    active = await User.objects.filter(is_active=True).order_by("-created_at").limit(20).all()
    admin = await User.objects.filter(email="admin@grunt.local").first()
    total = await User.objects.filter(is_active=False).count()
    user, created = await User.objects.get_or_create(email="a@b.com", defaults={"first_name": "A"})

Filter keys support the same operator suffixes as ``grunt.db`` (``__gt``, ``__gte``,
``__lt``, ``__lte``, ``__in``, ``__nin``, ``__like``, ``__ilike``, ``__isnull``, ``__ne``)
— they are passed straight through to ``build_clauses``, nothing extra to learn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grunt.document.base import Document


class QuerySet[T: Document]:
    """Immutable, chainable query builder bound to a single ``Document`` subclass."""

    def __init__(self, model_cls: type[T]) -> None:
        self._model_cls = model_cls
        self._doctype: str = getattr(model_cls, "doctype", model_cls.__name__)
        self._filters: dict[str, Any] = {}
        self._fields: list[str] | None = None
        self._order_by = "modified_at"
        self._order = "desc"
        self._limit = 20
        self._page = 1

    def _clone(self) -> QuerySet[T]:
        clone = QuerySet(self._model_cls)
        clone._filters = dict(self._filters)
        clone._fields = self._fields
        clone._order_by = self._order_by
        clone._order = self._order
        clone._limit = self._limit
        clone._page = self._page
        return clone

    # ── Chaining ─────────────────────────────────────────────────────────

    def filter(self, **kwargs: Any) -> QuerySet[T]:
        """Merge equality/operator-suffixed filters (e.g. ``created_at__gte=...``)."""
        clone = self._clone()
        clone._filters.update(kwargs)
        return clone

    def only(self, *fields: str) -> QuerySet[T]:
        """Restrict the SELECT to these columns instead of every column on the doctype."""
        clone = self._clone()
        clone._fields = list(fields)
        return clone

    def order_by(self, field: str) -> QuerySet[T]:
        """Sort by ``field`` ascending, or ``"-field"`` for descending."""
        clone = self._clone()
        if field.startswith("-"):
            clone._order_by, clone._order = field[1:], "desc"
        else:
            clone._order_by, clone._order = field, "asc"
        return clone

    def limit(self, n: int) -> QuerySet[T]:
        clone = self._clone()
        clone._limit = n
        return clone

    def page(self, n: int) -> QuerySet[T]:
        clone = self._clone()
        clone._page = n
        return clone

    # ── Execution ────────────────────────────────────────────────────────

    async def all(self) -> list[T]:
        from grunt.app import grunt

        return await grunt.get_all(
            self._model_cls,
            filters=self._filters or None,
            fields=self._fields,
            limit=self._limit,
            page=self._page,
            order_by=self._order_by,
            order=self._order,
        )

    async def first(self) -> T | None:
        results = await self.limit(1).all()
        return results[0] if results else None

    async def count(self) -> int:
        from grunt.app import grunt

        return await grunt.count(self._doctype, filters=self._filters or None)

    async def exists(self) -> bool:
        return await self.count() > 0

    async def create(self, **data: Any) -> T:
        """Create a new document and return it as a typed controller instance."""
        from grunt.app import grunt
        from grunt.context import require_session, require_user

        created = await grunt.new_doc(self._doctype, data)
        return self._model_cls(
            doctype=self._doctype,
            data=created,
            user=require_user(),
            session=require_session(),
        )

    async def get_or_create(
        self,
        defaults: dict[str, Any] | None = None,
        **lookup: Any,
    ) -> tuple[T, bool]:
        """Return ``(doc, False)`` if a match for ``lookup`` exists, else ``(doc, True)``."""
        existing = await self.filter(**lookup).first()
        if existing is not None:
            return existing, False
        created = await self.create(**{**lookup, **(defaults or {})})
        return created, True
