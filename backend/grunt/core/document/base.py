"""Base Document class — the foundation for all DocType controllers.

Every DocType can have a custom controller by subclassing :class:`Document`.
Field annotations on the subclass serve as both documentation and type hints for
IDEs — they are NOT regular class attributes; at runtime, all field access is
routed through ``self.data`` via ``__getattr__``/``__setattr__``.

Defining a typed controller::

    from grunt.core.document.base import Document
    from grunt.app import grunt

    class Invoice(Document):
        # Declare fields as class-level annotations for IDE support.
        # The declared type is used by type checkers; the value lives in self.data.
        number: str
        amount: float
        status: str
        customer: str          # Link → Customer
        due_date: str          # Date field (ISO string at runtime)
        notes: str | None

        async def validate(self) -> None:
            if self.amount is not None and self.amount <= 0:
                grunt.throw("Сума повинна бути більше нуля")

        async def before_insert(self) -> None:
            if not self.number:
                self.number = f"INV-{self.id[:8].upper()}"

        async def after_insert(self) -> None:
            await grunt.notify(
                users=[self.owner],
                subject=f"Рахунок {self.number} створено",
                message=f"Сума: {self.amount} грн.",
                doctype=self.doctype,
                doc_id=self.id,
            )

Accessing document data::

    # Read — goes through __getattr__, returns self.data.get("amount")
    amount = self.amount

    # Write — goes through __setattr__, sets self.data["amount"] = value
    self.amount = 1500.0

    # Access system fields
    doc_id = self.id
    created_by = self.owner
    is_draft = self.docstatus == 0

    # Access the raw data dict directly when needed
    raw = self.data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.app import GruntApp
    from grunt.core.doctypes.user.user import User

# Fields that are stored as real instance attributes (not routed into self.data)
_RESERVED = frozenset({"doctype", "data", "user", "session"})


class DocumentList(list):
    """A list of documents/rows with associated metadata (pagination, etc.)."""

    def __init__(self, data: list, meta: dict[str, Any] | None = None) -> None:
        super().__init__(data)
        self.meta = meta or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to the standard API response format."""
        return {"data": list(self), "meta": self.meta}

    def __getitem__(self, key: Any) -> Any:
        if key == "data":
            return list(self)
        if key == "meta":
            return self.meta
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "data":
            return list(self)
        if key == "meta":
            return self.meta
        return default


class Document:
    """Base class for all DocType controllers.

    Subclass this to add custom validation and lifecycle hooks to a DocType.
    Place the subclass in your app's ``controllers/`` directory (or register it
    manually via :func:`~grunt.core.document.registry.document_registry`).

    **Field annotations** — declare DocType fields as class-level annotations to
    get IDE autocompletion and type-checker support:

    .. code-block:: python

        class Order(Document):
            title: str
            amount: float
            status: str

    At runtime, attribute access is routed through ``self.data`` — the annotation
    is a type hint only.

    **Lifecycle hooks** (all async, all optional):

    * ``validate()`` — called on create and update, before DB write.
    * ``before_insert()`` — called on create only, before DB insert.
    * ``after_insert()`` — called after the row is inserted.
    * ``before_save()`` — called on create and update, just before DB write.
    * ``after_save()`` — called after a successful create or update.
    * ``before_delete()`` — called before the row is deleted.
    * ``after_delete()`` — called after deletion.
    """

    def __init__(
        self,
        doctype: str,
        data: dict[str, Any],
        user: User | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        # Use object.__setattr__ to bypass our custom __setattr__ for reserved attrs
        object.__setattr__(self, "doctype", doctype)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "user", user)
        object.__setattr__(self, "session", session)

    # ── Attribute routing ─────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails (i.e. for non-reserved names)
        try:
            return object.__getattribute__(self, "data")[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _RESERVED:
            object.__setattr__(self, name, value)
        else:
            object.__getattribute__(self, "data")[name] = value

    # ── Convenience accessors ─────────────────────────────────────────────

    @property
    def grunt(self) -> GruntApp:
        """The :class:`~grunt.app.GruntApp` singleton.

        A shorthand for ``from grunt.app import grunt``.

        Available inside all lifecycle hooks as ``self.grunt``.

        Example::

            async def validate(self) -> None:
                exists = await self.grunt.db.exists("Customer", self.customer)
                if not exists:
                    self.grunt.throw(f"Клієнта '{self.customer}' не знайдено")
        """
        from grunt.app import grunt as _grunt  # noqa: PLC0415

        return _grunt

    def as_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the underlying data dict."""
        return dict(object.__getattribute__(self, "data"))

    def update(self, values: dict[str, Any]) -> None:
        """Bulk-update multiple fields at once.

        Equivalent to calling ``self.field = value`` for each key in ``values``.
        """
        data = object.__getattribute__(self, "data")
        data.update(values)

    def get(self, fieldname: str, default: Any = None) -> Any:
        """Return ``self.data.get(fieldname, default)`` — same as ``dict.get``."""
        return object.__getattribute__(self, "data").get(fieldname, default)

    # ── Persistence ───────────────────────────────────────────────────────

    async def insert(self) -> dict[str, Any]:
        """Insert this document into the database and sync local data."""
        from grunt.app import grunt as _grunt  # noqa: PLC0415

        result = await _grunt.new_doc(self.doctype, self.data)
        object.__getattribute__(self, "data").update(result)
        return result

    async def save(self) -> dict[str, Any]:
        """Save changes to the database and sync local data."""
        from grunt.app import grunt as _grunt  # noqa: PLC0415

        result = await _grunt.save_doc(self.doctype, self.id, self.data)
        object.__getattribute__(self, "data").update(result)
        return result

    async def delete(self) -> None:
        """Delete this document from the database."""
        from grunt.app import grunt as _grunt  # noqa: PLC0415

        await _grunt.delete_doc(self.doctype, self.id)

    # ── Lifecycle hooks ───────────────────────────────────────────────────

    async def on_load(self) -> None:
        """Called after a document is loaded from the database.

        Override to apply defaults, coerce field types, or load related data
        (e.g. roles, computed fields).  At call time ``self.data`` contains
        the raw row dict from the DB.
        """

    async def before_insert(self) -> None:
        """Called before a new document is inserted into the database."""

    async def after_insert(self) -> None:
        """Called after a new document is inserted into the database."""

    async def before_save(self) -> None:
        """Called before a document is written to the database (create or update)."""

    async def after_save(self) -> None:
        """Called after a document is successfully written to the database."""

    async def before_delete(self) -> None:
        """Called before a document is deleted from the database."""

    async def after_delete(self) -> None:
        """Called after a document is deleted from the database."""

    async def validate(self) -> None:
        """Custom validation — raise :class:`~grunt.app.GruntError` to abort the save."""

    # ── Repr ──────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        doc_id = object.__getattribute__(self, "data").get("id", "?")
        doctype = object.__getattribute__(self, "doctype")
        return f"<{doctype} id={doc_id!r}>"
