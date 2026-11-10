"""``Document`` - the base class of every DocType controller.

A controller is the DocType's lifecycle hooks and business logic; where its
documents live is the DocType's store (:mod:`grunt.store`) - the table by
default, or the class a controller names in ``store_class`` (a
:class:`~grunt.store.VirtualStore` for rows from an API, Redis or files).

Field values live in ``self.data``; ``__getattr__``/``__setattr__`` route
``doc.amount`` to ``doc.data["amount"]``. Annotations on a subclass are only
there for IDEs and type checkers.
"""

import contextlib
import copy
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import grunt
from grunt.api.v1.ws import manager
from grunt.document.formula import evaluate_read_formulas
from grunt.document.mixins.collaboration_rpc import DocumentCollaborationRPCMixin
from grunt.document.mixins.export_rpc import DocumentExportRPCMixin
from grunt.document.mixins.history_rpc import DocumentHistoryRPCMixin
from grunt.document.mixins.lifecycle import DocumentLifecycleMixin
from grunt.document.mixins.link_rpc import DocumentLinkRPCMixin
from grunt.document.mixins.meta_rpc import DocumentMetaRPCMixin
from grunt.document.mixins.tree_rpc import DocumentTreeRPCMixin
from grunt.document.mixins.workflow_rpc import DocumentWorkflowRPCMixin
from grunt.document.queryset import QuerySet
from grunt.document.registry import document_registry
from grunt.document.serde import to_json, with_doctype
from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import _user_ctx, require_engine, require_session, session_user
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.store import Store, store_for
lazy from grunt.document.multi_link import MultiLinkService

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
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return dt


class _ObjectsDescriptor:
    """``Document.objects`` - returns a QuerySet for the controller class."""

    def __get__(self, instance: Any, owner: type[Document]) -> Any:
        return QuerySet(owner)


class Document(
    DocumentTreeRPCMixin,
    DocumentLinkRPCMixin,
    DocumentExportRPCMixin,
    DocumentHistoryRPCMixin,
    DocumentCollaborationRPCMixin,
    DocumentWorkflowRPCMixin,
    DocumentMetaRPCMixin,
    DocumentLifecycleMixin,
):
    """A document: its values in ``self.data``, its lifecycle hooks, and the
    pipeline that stores it.

    Subclass it and override the lifecycle hooks below (all async, all optional)::

        class Invoice(Document):
            amount: float
            customer: str

            async def validate(self) -> None:
                if self.amount <= 0:
                    throw("Сума повинна бути більше нуля")

    A DocType whose documents aren't rows of its table names its store::

        class BackupStore(VirtualStore):
            async def rows(self, query):
                return list_backups()

        class Backup(Document):
            store_class = BackupStore
    """

    #: The store of the DocType's documents - ``None``: its table (nothing at
    #: all for a virtual DocType).
    store_class: ClassVar[type[Store] | None] = None

    objects: ClassVar[_ObjectsDescriptor] = _ObjectsDescriptor()

    doctype: str
    data: dict[str, Any]
    # The mixins assume these are bound, but outside a grunt context _bind()
    # can leave them None, so they are left untyped here.
    session: Any
    engine: Any
    _ml: Any

    def __init__(
        self,
        doctype: str,
        data: dict[str, Any],
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> None:
        self.doctype = doctype
        self.data = data
        self.session = session
        self.engine = engine
        self._ml = None  # MultiLinkService, created in _bind() once there is a session
        self._dt = None
        self.input_data = {}
        self.doc_before_save = None

    @property
    def user(self) -> str | None:
        """Email of the user the context runs as. A document acts as the session
        user (as in Frappe) - it carries no user of its own."""
        return session_user()

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
        """The document as a JSON object naming its DocType - child rows included."""
        return copy.deepcopy(with_doctype(self.doctype, self.data))

    def as_json(self, *, indent: int | None = 2) -> str:
        return to_json(self.as_dict(), indent=indent)

    def update(self, values: dict[str, Any]) -> None:
        self.data.update(values)

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.data.get(fieldname, default)

    # Context binding

    def _bind(self) -> None:
        """Fill in session/engine from the active grunt context if not given.

        Lets the same controller work inside a request and from scripts/CLI
        running under ``grunt.context(...)``. Whatever can't be resolved stays
        None and only fails once it's actually used.
        """
        if self.session is None:
            with contextlib.suppress(RuntimeError):
                self.session = require_session()
        if self.engine is None:
            with contextlib.suppress(RuntimeError):
                self.engine = require_engine()
        if self._ml is None and self.session is not None:
            self._ml = MultiLinkService(self.session)

    def _set_grunt_context(self) -> tuple:
        """Bind this document's session/engine for its hooks; the user stays the context's."""
        return grunt.set_context(session=self.session, engine=self.engine, user=_user_ctx.get())

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
    ) -> Document:
        """Load a document as an instance of its registered controller."""
        return await load_document(doctype, name, expand=expand, session=session, engine=engine)

    @classmethod
    async def new(
        cls,
        doctype: str,
        data: dict[str, Any],
        *,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
    ) -> Document:
        """A new, unsaved instance of *doctype*'s registered controller holding *data*."""
        return await new_document(doctype, data, session=session, engine=engine)

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
        """Before every write. Call ``throw()`` to abort the save."""

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

    # Lists and trees of the table

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


document_registry.use_base(Document)


def controller_class(dt: Any) -> type[Document]:
    """The controller of the DocType *dt*."""
    return document_registry.get(dt.name)


async def new_document(
    doctype: str,
    data: dict[str, Any],
    *,
    session: AsyncSession | None = None,
    engine: AsyncEngine | None = None,
) -> Document:
    """An instance of *doctype*'s controller holding *data*, bound to the context."""
    doc = controller_class(await _meta(doctype))(doctype, data, session=session, engine=engine)
    doc._bind()
    return doc


async def load_document(
    doctype: str,
    name: str | None = None,
    *,
    expand: list[str] | None = None,
    session: AsyncSession | None = None,
    engine: AsyncEngine | None = None,
) -> Document:
    """The stored document *name* as an instance of its controller.

    A singleton needs no *name*. *expand* - the child tables and MultiLink
    fields to load: ``None`` - all, ``[]`` - the bare row (no read formulas
    either: those can run queries of their own, e.g. a permission check
    needs none of it).
    """
    dt = await _meta(doctype)
    doc = controller_class(dt)(doctype, {"name": name or doctype}, session=session, engine=engine)
    doc._bind()
    doc._dt = dt
    data = await store_for(dt, doc.session).get(name or doctype, expand=expand)
    if data is None:
        raise not_found(_("Document “%(name)s” not found") % {"name": name or dt.name})
    if expand is None or any(expand):
        await evaluate_read_formulas(dt.doc, data)
    doc.data = data
    if type(doc).on_load is not Document.on_load:
        await doc.on_load()
    doc.data = with_doctype(doctype, doc.data)
    return doc


def is_shadowed_field(fieldname: str) -> bool:
    """Whether a controller attribute hides the field - ``doc.user`` is the
    session user, ``doc.delete`` a method - so it is read as ``doc.data[...]``."""
    return fieldname not in SYS_FIELDS and (fieldname in _RESERVED or hasattr(Document, fieldname))
