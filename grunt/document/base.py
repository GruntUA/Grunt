"""Base Document class — the foundation for all DocType controllers.

Every DocType can have a custom controller by subclassing :class:`Document`.
Field annotations on the subclass serve as both documentation and type hints for
IDEs — they are NOT regular class attributes; at runtime, all field access is
routed through ``self.data`` via ``__getattr__``/``__setattr__``.

Defining a typed controller::

    from grunt.document.base import Document
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

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from grunt.context import require_engine, require_session, require_user
from grunt.document.mixins.collaboration_rpc import DocumentCollaborationRPCMixin
from grunt.document.mixins.export_rpc import DocumentExportRPCMixin
from grunt.document.mixins.history_rpc import DocumentHistoryRPCMixin
from grunt.document.mixins.link_rpc import DocumentLinkRPCMixin
from grunt.document.mixins.meta_rpc import DocumentMetaRPCMixin
from grunt.document.mixins.tree_rpc import DocumentTreeRPCMixin
from grunt.document.mixins.workflow_rpc import DocumentWorkflowRPCMixin
from grunt.document.mixins.write import DocumentWriteMixin
from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.app import GruntApp
    from grunt.auth.doctypes.User.user import User


# Fields that are stored as real instance attributes (not routed into self.data)
_RESERVED = frozenset({"doctype", "data", "user", "session", "engine"})

# System fields managed by the framework — exposed as read-only properties on Document.
# Controllers must not set these directly; use self.data["field"] = ... if truly needed.
SYS_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "owner",
        "docstatus",
        "idx",
        "created_at",
        "modified_at",
        "modified_by",
        "parent",
        "parentfield",
        "parenttype",
    }
)


class DocumentList(list):
    """A list of documents/rows with associated metadata (pagination, etc.).

    Deliberately dual-interface, not a plain list: ``for doc in result`` and
    ``result[0]`` behave like a normal list, but ``result["data"]`` and
    ``result["meta"]``/``result.meta`` are special-cased to make this object
    also usable wherever callers expect the ``{"data": [...], "meta": {...}}``
    API response shape (see :meth:`to_dict`) without a separate conversion
    step. This means ``result["data"]`` is NOT indexing into the list by a
    literal string key the way a real ``dict`` would raise for — don't assume
    ``DocumentList`` behaves like ``dict`` beyond these two special keys.
    """

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


class _ObjectsDescriptor:
    """Class-level descriptor backing ``Document.objects`` — see ``QuerySet``.

    Only ever bound via class access (``User.objects``, not ``user.objects``);
    it does not go through ``Document.__getattr__`` (that only fires on
    *instance* attribute lookup misses), so there's no risk of colliding with
    a real ``objects`` field on a doctype.
    """

    def __get__(self, instance: Any, owner: type[Document]) -> Any:
        from grunt.document.queryset import QuerySet

        return QuerySet(owner)


class Document(
    DocumentWriteMixin,
    DocumentTreeRPCMixin,
    DocumentLinkRPCMixin,
    DocumentExportRPCMixin,
    DocumentHistoryRPCMixin,
    DocumentCollaborationRPCMixin,
    DocumentWorkflowRPCMixin,
    DocumentMetaRPCMixin,
):
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

    objects: ClassVar[_ObjectsDescriptor] = _ObjectsDescriptor()

    def __init__(
        self,
        doctype: str,
        data: dict[str, Any],
        user: User | None = None,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        # Use object.__setattr__ to bypass our custom __setattr__ for reserved attrs
        object.__setattr__(self, "doctype", doctype)
        object.__setattr__(self, "data", data)
        object.__setattr__(self, "user", user)
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "engine", engine)
        # MultiLinkService bound lazily in _bind() once a session is resolved.
        object.__setattr__(self, "_ml", None)

    @classmethod
    def bare(
        cls,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> Document:
        """Build an empty, bound throwaway document to run dict-based pipeline methods on.

        Single builder for the ``GruntApp`` facade and REST layer, both
        of which drive the CRUD pipeline through a throwaway ``Document``. Passing
        ``session``/``engine`` binds them explicitly; omitting them lets ``_bind``
        resolve the active grunt context.
        """
        doc = cls("", {}, session=session, engine=engine)
        doc._bind()
        return doc

    # ── Attribute routing ─────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails (i.e. for non-reserved names).
        # Private attributes (underscore-prefixed) are not routed through data.
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._raw()[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _RESERVED or name.startswith("_"):
            object.__setattr__(self, name, value)
        elif name in SYS_FIELDS:
            raise AttributeError(
                f"'{name}' is a system field and cannot be set directly. "
                f"Use self.data['{name}'] = ... if you must override it."
            )
        else:
            self._raw()[name] = value

    def _raw(self, name: str = "data") -> Any:
        """Read a reserved attribute (``data``/``session``/``doctype``/…) directly.

        ``self.data`` already resolves correctly via plain attribute lookup —
        reserved names (see ``_RESERVED`` above) are always real instance
        attributes, never routed through the data dict — but spelling that
        out as ``self._raw()`` at every call site
        buried the actual intent ("read the raw dict") under bypass-boilerplate
        repeated ~25 times in this file. One named escape hatch instead.
        """
        return object.__getattribute__(self, name)

    # ── System field accessors (read-only) ───────────────────────────────

    @property
    def id(self) -> str | None:
        """Document identifier — alias for name (primary key)."""
        return self._raw().get("name")

    @property
    def name(self) -> str | None:
        """Human-readable document identifier (primary key)."""
        return self._raw().get("name")

    @property
    def owner(self) -> str | None:
        """Username of the user who created this document."""
        return self._raw().get("owner")

    @property
    def docstatus(self) -> int:
        """Workflow state: 0 = Draft, 1 = Submitted, 2 = Cancelled."""
        return self._raw().get("docstatus", 0)

    @property
    def idx(self) -> int:
        """Row index within a parent document's child table."""
        return self._raw().get("idx", 0)

    @property
    def created_at(self) -> Any:
        """Timestamp when the document was first created."""
        return self._raw().get("created_at")

    @property
    def modified_at(self) -> Any:
        """Timestamp of the most recent save."""
        return self._raw().get("modified_at")

    @property
    def modified_by(self) -> str | None:
        """Username of the user who last saved this document."""
        return self._raw().get("modified_by")

    @property
    def parent(self) -> str | None:
        """ID of the parent document (set for child-table rows only)."""
        return self._raw().get("parent")

    @property
    def parentfield(self) -> str | None:
        """Field name in the parent DocType that references this child table."""
        return self._raw().get("parentfield")

    @property
    def parenttype(self) -> str | None:
        """DocType name of the parent document."""
        return self._raw().get("parenttype")

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
        from grunt.app import grunt as _grunt

        return _grunt

    def as_dict(self) -> dict[str, Any]:
        """Return a shallow copy of the underlying data dict."""
        return dict(self._raw())

    def update(self, values: dict[str, Any]) -> None:
        """Bulk-update multiple fields at once.

        Equivalent to calling ``self.field = value`` for each key in ``values``.
        """
        data = self._raw()
        data.update(values)

    def get(self, fieldname: str, default: Any = None) -> Any:
        """Return ``self.data.get(fieldname, default)`` — same as ``dict.get``."""
        return self._raw().get(fieldname, default)

    # ── Context binding ───────────────────────────────────────────────────

    def _bind(self) -> None:
        """Populate session/engine/user/_ml from explicit attrs or the active grunt context.

        Lets a document be persisted both inside an HTTP request (where the
        controller is built with session/engine) and from a script/CLI that runs
        within ``async with grunt.context(...)``.

        The ambient ``ContextVar`` fallback below exists for callers that have
        no session/engine/user to pass explicitly (scripts, CLI, background
        tasks). Prefer constructing with explicit ``session``/``engine``/``user``
        wherever they're available — including in tests, where relying on
        ambient context means pushing values into ``ContextVar``s instead of
        passing them in directly. Each of the three resolves independently and
        silently no-ops on failure, so a ``Document()`` built with no arguments
        can end up only partially bound (e.g. session set, user not) with no
        error until the missing piece is actually used.
        """
        if (
            getattr(self, "session", None) is None
            or getattr(self, "engine", None) is None
            or getattr(self, "user", None) is None
        ):
            if getattr(self, "session", None) is None:
                with contextlib.suppress(Exception):
                    object.__setattr__(self, "session", require_session())
            if getattr(self, "engine", None) is None:
                with contextlib.suppress(Exception):
                    object.__setattr__(self, "engine", require_engine())
            if getattr(self, "user", None) is None:
                with contextlib.suppress(Exception):
                    object.__setattr__(self, "user", require_user())
        if getattr(self, "_ml", None) is None and getattr(self, "session", None) is not None:
            from grunt.document.multi_link import MultiLinkService

            object.__setattr__(self, "_ml", MultiLinkService(self.session))

    def _set_grunt_context(self, user: User) -> tuple:
        """Activate the grunt ContextVar context for the current lifecycle scope."""
        from grunt.app import grunt as _grunt

        return _grunt.set_context(session=self.session, engine=self.engine, user=user)

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        from grunt.app import grunt as _grunt

        _grunt.reset_context(tokens)

    # ── Persistence ───────────────────────────────────────────────────────

    async def insert(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Insert this document into the database and sync local data.

        Runs the full create pipeline (validate/before_insert/before_save →
        INSERT → child tables → aggregations → MultiLink → after hooks) directly
        on this object. Returns the persisted document dict.
        """
        self._bind()
        result = await self.create_document(
            self.doctype, self.data, self.user, ignore_required=ignore_required
        )
        data = self._raw()
        data.clear()
        data.update(result)
        return result

    async def save(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Save changes to the database and sync local data.

        Runs the full update pipeline (validate/before_save → UPDATE → children →
        aggregations → MultiLink → after_save) on this object's current state.
        """
        self._bind()
        doc_id = self.id
        if doc_id is None:
            raise ValueError(f"Cannot save {self.doctype}: document has no name")
        result = await self.update_document(
            self.doctype, doc_id, self.data, self.user, ignore_required=ignore_required
        )
        data = self._raw()
        data.clear()
        data.update(result)
        return result

    async def delete(self) -> None:
        """Delete this document from the database."""
        self._bind()
        doc_id = self.id
        if doc_id is None:
            raise ValueError(f"Cannot delete {self.doctype}: document has no name")
        await self.delete_document(self.doctype, doc_id, self.user)

    @classmethod
    async def load(
        cls,
        doctype: str,
        name: str,
        *,
        expand: list[str] | None = None,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
        user: User | None = None,
    ) -> Document:
        """Load a document from the DB and return it as its controller instance.

        The returned object is an instance of the registered controller subclass
        with ``self.data`` populated (child tables, MultiLink, read formulas, and
        ``on_load`` already applied), ready for ``.save()``/``.delete()``.
        """
        from grunt.document.registry import document_registry

        controller_cls = document_registry.get(doctype)
        inst = controller_cls(doctype, {}, user=user, session=session, engine=engine)
        inst._bind()
        loaded = await inst.get_document(doctype, name, inst.user, expand=expand)
        data = inst._raw()
        data.clear()
        data.update(loaded)
        return inst

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

    @classmethod
    async def list_filter_extra(
        cls,
        session: Any,
        filters: dict[str, Any],
        table: Any,
    ) -> Any | None:
        """Return an extra SQLAlchemy WHERE clause to append to list/tree queries.

        Override in a controller to inject custom per-DocType filtering that
        cannot be expressed as simple ``field__op=value`` pairs.  Return a
        SQLAlchemy ``ClauseElement`` or ``None`` to skip.

        The clause is appended *before* the standard ``apply_filters`` step
        so that both the data query and the COUNT query are guarded.

        Example::

            @classmethod
            async def list_filter_extra(cls, session, filters, table):
                from sqlalchemy import or_
                col = table.c.get("archived")
                if col is None:
                    return None
                return or_(col == False, col.is_(None))
        """
        return None

    @classmethod
    async def tree_preserve_ancestors(
        cls,
        session: Any,
        filters: dict[str, Any],
        table: Any,
    ) -> bool:
        """Return whether matched tree nodes should include ancestor chain.

        Override in a controller when tree filters should return strictly
        matching nodes (for example, time-sliced hierarchy views where
        non-matching ancestors must stay hidden).
        """
        return True

    @classmethod
    async def tree_get_sort_order(
        cls,
        session: Any,
        filters: dict[str, Any],
        table: Any,
        *,
        sort_by: str | None,
        sort_order: str,
    ) -> tuple[str | None, str] | None:
        """Return custom tree sort settings as ``(sort_by, sort_order)``.

        Override in a DocType controller to provide app-specific ordering for
        tree nodes. Return ``None`` to keep the resolved defaults.
        """
        return None

    @classmethod
    async def tree_sort_children(
        cls,
        session: Any,
        children: list[dict[str, Any]],
        *,
        parent: dict[str, Any] | None,
        sort_by: str | None,
        sort_order: str,
    ) -> list[dict[str, Any]]:
        """Return reordered child nodes for advanced tree sorting use-cases.

        Override to apply business-specific sorting that cannot be expressed as
        a single ``sort_by`` field. The default implementation is a no-op.
        """
        return children

    # ── Real-time helpers ─────────────────────────────────────────────────

    async def publish_progress(
        self,
        processed: int,
        total: int,
        *,
        message: str | None = None,
        commit: bool = True,
    ) -> None:
        """Broadcast import/processing progress via WebSocket.

        Updates ``processed_rows`` / ``total_rows`` on the document (if those
        fields exist), persists to DB, then sends an ``import_progress`` event
        on the document's WebSocket channel so connected clients update their
        progress UI without polling.

        Usage inside a controller::

            for idx, row in enumerate(rows):
                await self.process_row(row)
                if idx % 10 == 0:
                    await self.publish_progress(idx + 1, len(rows))

        Arguments:
            processed: Number of items processed so far.
            total:     Total number of items to process.
            message:   Optional status string shown alongside the progress bar.
            commit:    Whether to flush the session to DB (default ``True``).
                       Pass ``False`` if you handle the commit yourself.
        """
        data = self._raw()
        if "processed_rows" in data or hasattr(self, "processed_rows"):
            data["processed_rows"] = processed
        if "total_rows" in data or hasattr(self, "total_rows"):
            data["total_rows"] = total

        session = self._raw("session")
        if commit and session is not None:
            await session.commit()

        try:
            from grunt.api.v1.ws import manager

            doc_id = data.get("name")
            if doc_id:
                payload: dict[str, object] = {
                    "processed": processed,
                    "total": total,
                }
                if message is not None:
                    payload["message"] = message
                await manager.broadcast_doc(
                    self._raw("doctype"),
                    str(doc_id),
                    "import_progress",
                    payload,
                )
        except Exception:
            log.exception("suppressed_error")

    # ── Repr ──────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        doc_id = self._raw().get("name", "?")
        doctype = self._raw("doctype")
        return f"<{doctype} id={doc_id!r}>"
