"""Base classes for DocType controllers.

``BaseDocument`` is a document with its lifecycle and no storage of its own -
the base of a controller backed by an API, Redis or files (a virtual DocType).
``Document`` is a ``BaseDocument`` stored in the DocType's table, the default
for every DocType.

Field values live in ``self.data``; ``__getattr__``/``__setattr__`` route
``doc.amount`` to ``doc.data["amount"]``. Annotations on a subclass are only
there for IDEs and type checkers.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

import grunt
from grunt import _, log
from grunt.api.v1.ws import manager
from grunt.document.mixins.collaboration_rpc import DocumentCollaborationRPCMixin
from grunt.document.mixins.export_rpc import DocumentExportRPCMixin
from grunt.document.mixins.history_rpc import DocumentHistoryRPCMixin
from grunt.document.mixins.lifecycle import DocumentLifecycleMixin
from grunt.document.mixins.link_rpc import DocumentLinkRPCMixin
from grunt.document.mixins.meta_rpc import DocumentMetaRPCMixin
from grunt.document.mixins.tree_rpc import DocumentTreeRPCMixin
from grunt.document.mixins.workflow_rpc import DocumentWorkflowRPCMixin
from grunt.document.mixins.write import DocumentWriteMixin
from grunt.document.queryset import QuerySet
from grunt.document.registry import document_registry
from grunt.errors import not_found
from grunt.local import require_engine, require_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from grunt.auth.doctypes.User.user import User


# Real instance attributes; everything else is routed into self.data.
_RESERVED = frozenset(
    {"doctype", "data", "user", "session", "engine", "input_data", "doc_before_save"}
)

# Read-only on the controller. Set them through self.data if you really must.
SYS_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "owner",
        "idx",
        "created_at",
        "modified_at",
        "modified_by",
        "parent",
        "parentfield",
        "parenttype",
    }
)


async def _meta(doctype: str) -> Any:
    dt = await grunt.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return dt


class DocumentList(list):
    """A list of rows plus pagination meta.

    Iterates and indexes like a list, but ``result["data"]`` and
    ``result["meta"]`` also work, so it can be returned where the
    ``{"data": ..., "meta": ...}`` response shape is expected.
    """

    def __init__(self, data: list, meta: dict[str, Any] | None = None) -> None:
        super().__init__(data)
        self.meta = meta or {}

    def to_dict(self) -> dict[str, Any]:
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
    """``Document.objects`` - returns a QuerySet for the controller class."""

    def __get__(self, instance: Any, owner: type[BaseDocument]) -> Any:
        return QuerySet(owner)


class BaseDocument(DocumentLifecycleMixin):
    """A document with its lifecycle hooks and no storage of its own.

    Subclass it for a DocType whose documents live somewhere else and override
    the storage methods - see :mod:`grunt.document.mixins.lifecycle`::

        class Backup(BaseDocument):
            @classmethod
            async def get_list(cls, doctype, *, page=1, per_page=20, **kwargs):
                return build_response(list_backups(), page, per_page)

            async def load_from_db(self, *, expand=None):
                self.data = get_backup(self.name)
    """

    objects: ClassVar[_ObjectsDescriptor] = _ObjectsDescriptor()

    doctype: str
    data: dict[str, Any]
    # The mixins assume these are bound, but outside a grunt context _bind()
    # can leave them None, so they are left untyped here.
    user: Any
    session: Any
    engine: Any
    _ml: Any

    def __init__(
        self,
        doctype: str,
        data: dict[str, Any],
        user: User | None = None,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        self.doctype = doctype
        self.data = data
        self.user = user
        self.session = session
        self.engine = engine
        self._ml = None  # MultiLinkService, created in _bind() once there is a session
        self._dt = None
        self.input_data = {}
        self.doc_before_save = None

    # Attribute routing

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup fails, i.e. for field names. Reserved
        # names land here before __init__ has set them (copy, pickle).
        if name.startswith("_") or name in _RESERVED:
            raise AttributeError(name)
        return self.data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _RESERVED or name.startswith("_"):
            object.__setattr__(self, name, value)
        elif name in SYS_FIELDS:
            raise AttributeError(
                f"'{name}' is a system field and cannot be set directly. "
                f"Use self.data['{name}'] = ... if you must override it."
            )
        else:
            self.data[name] = value

    # System fields (read-only)

    @property
    def id(self) -> str | None:
        """Same as ``name``."""
        return self.data.get("name")

    @property
    def name(self) -> str | None:
        return self.data.get("name")

    @property
    def owner(self) -> str | None:
        return self.data.get("owner")

    @property
    def idx(self) -> int:
        """Row position in the parent's child table."""
        return self.data.get("idx", 0)

    @property
    def created_at(self) -> Any:
        return self.data.get("created_at")

    @property
    def modified_at(self) -> Any:
        return self.data.get("modified_at")

    @property
    def modified_by(self) -> str | None:
        return self.data.get("modified_by")

    @property
    def parent(self) -> str | None:
        return self.data.get("parent")

    @property
    def parentfield(self) -> str | None:
        return self.data.get("parentfield")

    @property
    def parenttype(self) -> str | None:
        return self.data.get("parenttype")

    @property
    def grunt(self):
        """The ``grunt`` package, so hooks can call ``self.grunt.db...``."""
        return grunt

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)

    def update(self, values: dict[str, Any]) -> None:
        self.data.update(values)

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.data.get(fieldname, default)

    # Context binding

    def _bind(self) -> None:
        """Fill in session/engine/user from the active grunt context if not given.

        Lets the same controller work inside a request and from scripts/CLI
        running under ``grunt.context(...)``. Whatever can't be resolved stays
        None and only fails once it's actually used.
        """
        if self.session is None:
            with contextlib.suppress(RuntimeError):
                self.session = grunt.get_session()
        if self.engine is None:
            with contextlib.suppress(RuntimeError):
                self.engine = require_engine()
        if self.user is None:
            with contextlib.suppress(RuntimeError):
                self.user = require_user()
        if self._ml is None and self.session is not None:
            from grunt.document.multi_link import MultiLinkService

            self._ml = MultiLinkService(self.session)

    def _set_grunt_context(self, user: User) -> tuple:
        return grunt.set_context(session=self.session, engine=self.engine, user=user)

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        grunt.reset_context(tokens)

    def _replace_data(self, values: dict[str, Any]) -> None:
        # Mutate in place: callers may still hold a reference to self.data.
        self.data.clear()
        self.data.update(values)

    # Persistence

    def _keep(self, original: dict[str, Any], result: dict[str, Any]) -> None:
        # Back into the caller's dict: callers may still hold a reference to self.data.
        if original is not result:
            original.clear()
            original.update(result)
        self.data = original

    async def insert(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Run the full create pipeline on this document and return the saved row."""
        original = self.data
        result = await self._insert(ignore_required=ignore_required)
        self._keep(original, result)
        return result

    async def save(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Run the full update pipeline on this document and return the saved row."""
        if self.id is None:
            raise ValueError(f"Cannot save {self.doctype}: document has no name")
        original = self.data
        result = await self._update(self.id, dict(original), ignore_required=ignore_required)
        self._keep(original, result)
        return result

    async def delete(self, *, replace_with: str | None = None) -> None:
        """Run the full delete pipeline on this document.

        ``replace_with`` - id of a surviving document (same DocType) that every
        reference to this one is repointed to before it is removed.
        """
        if self.id is None:
            raise ValueError(f"Cannot delete {self.doctype}: document has no name")
        original = self.data
        try:
            await self._delete(replace_with=replace_with)
        finally:
            self.data = original

    @classmethod
    async def load(
        cls,
        doctype: str,
        name: str | None = None,
        *,
        expand: list[str] | None = None,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
        user: User | None = None,
    ) -> BaseDocument:
        """Load a document as an instance of its registered controller."""
        return await load_document(
            doctype, name, expand=expand, session=session, engine=engine, user=user
        )

    # Lifecycle hooks

    async def on_load(self) -> None:
        """After the row is read from the DB; ``self.data`` holds the raw row."""

    async def before_insert(self) -> None:
        """Before INSERT of a new document."""

    async def after_insert(self) -> None:
        """After INSERT of a new document."""

    async def before_save(self) -> None:
        """Before every write, insert or update."""

    async def after_save(self) -> None:
        """After every successful write, insert or update."""

    async def before_delete(self) -> None:
        """Before the row is deleted."""

    async def after_delete(self) -> None:
        """After the row is deleted."""

    async def validate(self) -> None:
        """Before every write. Call ``grunt.throw()`` to abort the save."""

    async def publish_progress(
        self,
        processed: int,
        total: int,
        *,
        message: str | None = None,
        commit: bool = True,
    ) -> None:
        """Send an ``import_progress`` event to clients watching this document.

        Also sets ``processed_rows``/``total_rows`` in ``self.data`` when the
        DocType has those fields, and commits the session unless ``commit=False``.
        The fields themselves are not written until the document is saved.
        """
        if "processed_rows" in self.data:
            self.data["processed_rows"] = processed
        if "total_rows" in self.data:
            self.data["total_rows"] = total

        if commit and self.session is not None:
            await self.session.commit()

        doc_id = self.data.get("name")
        if not doc_id:
            return

        payload: dict[str, object] = {"processed": processed, "total": total}
        if message is not None:
            payload["message"] = message
        try:
            await manager.broadcast_doc(self.doctype, str(doc_id), "import_progress", payload)
        except Exception:
            log.exception("document.progress_broadcast_failed", doctype=self.doctype, doc=doc_id)

    def __repr__(self) -> str:
        return f"<{self.doctype} id={self.data.get('name', '?')!r}>"


class Document(
    DocumentWriteMixin,
    DocumentTreeRPCMixin,
    DocumentLinkRPCMixin,
    DocumentExportRPCMixin,
    DocumentHistoryRPCMixin,
    DocumentCollaborationRPCMixin,
    DocumentWorkflowRPCMixin,
    DocumentMetaRPCMixin,
    BaseDocument,
):
    """A document stored in its DocType's table - the default controller.

    Subclass it and override the lifecycle hooks below (all async, all optional)::

        class Invoice(Document):
            amount: float
            customer: str

            async def validate(self) -> None:
                if self.amount <= 0:
                    grunt.throw("Сума повинна бути більше нуля")
    """

    # Lists

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        session: AsyncSession,
        user: User,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        fields: list[str] | None = None,
        cursor: str | None = None,
        include_total: bool = True,
        **kwargs: Any,
    ) -> DocumentList:
        """A page of the documents *user* may see, read from the DocType's table."""
        from grunt.document.collection import table_list

        return await table_list(
            session,
            await _meta(doctype),
            user,
            page=page,
            per_page=per_page,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=filters,
            search=search,
            fields=fields,
            cursor=cursor,
            include_total=include_total,
        )

    @classmethod
    async def get_count(
        cls,
        doctype: str,
        *,
        session: AsyncSession,
        user: User,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> int:
        """How many documents *user* may see, under the same rules as :meth:`get_list`."""
        from grunt.document.collection import table_count

        return await table_count(
            session, await _meta(doctype), user, filters=filters, search=search
        )

    @classmethod
    async def list_filter_extra(
        cls,
        session: Any,
        filters: dict[str, Any],
        table: Any,
    ) -> Any | None:
        """Extra WHERE clause for list and tree queries, or None.

        For filtering that can't be written as ``field__op=value``. The clause
        is applied to both the data query and the COUNT query::

            @classmethod
            async def list_filter_extra(cls, session, filters, table):
                col = table.c.get("archived")
                return None if col is None else or_(col == False, col.is_(None))
        """
        return None

    @classmethod
    async def tree_preserve_ancestors(
        cls,
        session: Any,
        filters: dict[str, Any],
        table: Any,
    ) -> bool:
        """Whether a filtered tree also returns the ancestors of matched nodes."""
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
        """Override tree sorting as ``(sort_by, sort_order)``; None keeps the default."""
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
        """Reorder child nodes when one ``sort_by`` field isn't enough."""
        return children


def controller_class(dt: Any) -> type[BaseDocument]:
    """The controller of the DocType *dt*.

    A virtual DocType without a controller of its own has no documents - it
    gets ``BaseDocument``, not the table-backed default.
    """
    controller_cls = document_registry.get(dt.name)
    if controller_cls is Document and dt.is_virtual:
        return BaseDocument
    return controller_cls


def is_table_backed(dt: Any) -> bool:
    """True when *dt*'s documents are rows of its table - its controller is a
    ``Document`` - so table-only work (row lookups, batched DELETE, rename,
    trees) applies; False for a controller that keeps them elsewhere."""
    return issubclass(controller_class(dt), Document)


async def new_document(
    doctype: str,
    data: dict[str, Any],
    *,
    user: User | None = None,
    session: AsyncSession | None = None,
    engine: AsyncEngine | None = None,
) -> BaseDocument:
    """An instance of *doctype*'s controller holding *data*, bound to the context."""
    doc = controller_class(await _meta(doctype))(
        doctype, data, user=user, session=session, engine=engine
    )
    doc._bind()
    return doc


async def load_document(
    doctype: str,
    name: str | None = None,
    *,
    expand: list[str] | None = None,
    session: AsyncSession | None = None,
    engine: AsyncEngine | None = None,
    user: User | None = None,
) -> BaseDocument:
    """The stored document *name* as an instance of its controller.

    A singleton needs no *name*. *expand* - see ``load_from_db``.
    """
    dt = await _meta(doctype)
    doc = controller_class(dt)(
        doctype, {"name": name or doctype}, user=user, session=session, engine=engine
    )
    doc._bind()
    doc._dt = dt
    await doc.load_from_db(expand=expand)
    if type(doc).on_load is not BaseDocument.on_load:
        await doc.on_load()
    return doc
