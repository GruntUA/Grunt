"""``Document`` - the base class of every DocType controller.

A controller is the DocType's lifecycle hooks and business logic; where its
documents live is the DocType's store (:mod:`grunt.store`) - the table by
default, or the class a controller names in ``store_class`` (a
:class:`~grunt.store.VirtualStore` for rows from an API, Redis or files).

Field values live in ``self.data``; ``__getattr__``/``__setattr__`` route
``doc.amount`` to ``doc.data["amount"]``. Annotations on a subclass are only
there for IDEs and type checkers.
"""

import annotationlib
import contextlib
import copy
import sys
import typing
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Self, dataclass_transform

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.document import pipeline
from grunt.document.formula import evaluate_read_formulas
from grunt.document.mixins.lifecycle import DocumentLifecycleMixin, plain, row_of
from grunt.document.registry import document_registry
from grunt.document.serde import to_json, with_doctype
from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import _user_ctx, bind, require_engine, require_session, unbind
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.permissions.guards import write_guard
from grunt.store.base import Store
from grunt.store.lookup import store_for
lazy from grunt.document.multi_link import MultiLinkService

# Real instance attributes; everything else is routed into self.data.
_RESERVED = frozenset({"doctype", "data", "session", "engine", "input_data", "doc_before_save"})

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


# The document API (grunt.document.api.documents) behind Cls.get_doc / find_doc /
# get_list - it registers itself (:func:`use_document_api`): it imports this module.
_documents: Any = None


def use_document_api(api: Any) -> None:
    """Register the document API the class reads (``Invoice.get_list()``) go through."""
    global _documents
    _documents = api


def _api() -> Any:
    if _documents is None:
        raise RuntimeError("grunt.document.api is not loaded yet")
    return _documents


async def _meta(doctype: str) -> Any:
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return dt


@dataclass_transform(kw_only_default=True)
class Document(
    DocumentLifecycleMixin,
):
    """A document: its values in ``self.data``, its lifecycle hooks, and the
    pipeline that stores it.

    Subclass it and override the lifecycle hooks below (all async, all optional)::

        class Invoice(Document):
            amount: float
            customer: str
            note: str | None = None
            lines: list[InvoiceLine] = []

            async def validate(self) -> None:
                if self.amount <= 0:
                    throw("Сума повинна бути більше нуля")
                for line in self.lines or []:
                    line.total = line.qty * line.price  # stored with the invoice

    The field annotations (``grunt doctype sync-types`` writes them) also
    type the constructor, as for a dataclass - a field without ``= None`` /
    ``= []`` must be given::

        invoice = Invoice(amount=100, customer="CUST-1")   # unsaved
        await invoice.insert()
        invoice = await Invoice.create(amount=100, customer="CUST-1")  # saved
        invoice = Invoice(**row)                    # a row already read

    The defaults are for the type checker only: the class keeps none of them,
    a field is always read from ``self.data``.

    A child table typed ``list[ChildCls]`` holds documents of *ChildCls* while
    the controller holds the document - each over its row in ``self.data``, so
    a field set on a child is stored; ``append`` / ``remove`` / assigning the
    list are stored too. Validation, the store, the API and event handlers see
    the rows as dicts. A table typed ``list[dict]`` keeps dicts.

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

    #: The DocType this controller is for: the class name, a controller's
    #: subclass keeps its parent's, the registry sets it on what it registers.
    #: Read lists and documents by the class: ``Invoice.get_list()``.
    __doctype__: ClassVar[str] = "Document"

    doctype: str
    data: dict[str, Any]
    # The mixins assume these are bound, but outside a grunt context _bind()
    # can leave them None, so they are left untyped here. The class defaults
    # serve the documents :meth:`_from_rows` builds without ``__init__``.
    session: Any = None
    engine: Any = None
    _ml: Any = None
    _dt: Any = None
    doc_before_save: dict[str, Any] | None = None
    # A row of a list read: only the columns asked for, no child tables.
    _partial: bool = False
    # Fields the reader may not see (removed from ``data``): they read as None.
    _hidden: frozenset[str] = frozenset()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "__doctype__" not in cls.__dict__:
            parents = (b for b in cls.__mro__[1:] if b is not Document and issubclass(b, Document))
            cls.__doctype__ = next((b.__doctype__ for b in parents), cls.__name__)
        # `note: str | None = None` / `lines: list[InvoiceLine] = []` make a field
        # optional in the constructor; as class attributes they would hide
        # self.data (__getattr__ only runs when normal lookup fails).
        own = cls.__dict__
        for name in annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF):
            if name[:1] != "_" and name in own and (own[name] is None or own[name] == []):
                delattr(cls, name)

    def __new__(cls, doctype: str | None = None, *args: Any, **kwargs: Any) -> Any:
        # The registered controller when it extends the class called
        # (doctype_mixins / override_doctype_class of other apps), so their
        # hooks run - as for a document grunt loads. With or without an
        # explicit doctype; `Document("X", ...)` itself stays a bare Document.
        target = cls
        name: str = doctype or cls.__doctype__
        if cls is not Document:
            controller = document_registry.get(name)
            if controller is not cls and issubclass(controller, cls):
                target = controller
        doc = super().__new__(target)
        if doctype is None:
            doc._doctype = name
        return doc

    def __init__(
        self,
        doctype: str | None = None,
        data: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
        engine: AsyncEngine | None = None,
        **fields: Any,
    ) -> None:
        called_as: str | None = self.__dict__.pop("_doctype", None)
        self.doctype = doctype or called_as or type(self).__doctype__
        if fields:
            data = {**(data or {}), **fields}
        # Kept as given: callers may still hold a reference to it.
        self.data = data if data is not None else {}
        self.session = session
        self.engine = engine
        self._ml = None  # MultiLinkService, created in _bind() once there is a session
        self._dt = None
        self.input_data = {}  # what an insert / update was given - the lifecycle sets it
        self.doc_before_save = None
        self._wrap_children()

    @classmethod
    def _from_rows(
        cls,
        rows: Iterable[dict[str, Any]],
        *,
        doctype: str | None = None,
        partial: bool = False,
        hidden: frozenset[str] = frozenset(),
    ) -> list[Self]:
        """Rows read from the store as documents of this class - cheaply, without
        ``__init__`` (a list of thousands of rows). Each row becomes the document's
        ``data`` as is, not copied.

        The registered controller is used when it extends this class (app
        mixins / overrides), as for a document grunt loads. *partial* - a row of
        a list read (only the columns asked for, no child tables): a field it
        lacks raises instead of reading as None, and it can't be saved.
        """
        name = doctype or cls.__doctype__
        target: type[Self] = cls
        if cls is not Document:
            controller = document_registry.get(name)
            if controller is not cls and issubclass(controller, cls):
                target = controller
        new = object.__new__
        docs: list[Self] = []
        for row in rows:
            doc = new(target)
            state = doc.__dict__
            state["doctype"] = name
            state["data"] = row
            if partial:
                state["_partial"] = True
            else:  # a whole document may be saved: its own input_data, as __init__ gives
                state["input_data"] = {}
            if hidden:
                state["_hidden"] = hidden
            if _child_tables(target):
                doc._wrap_children()
            docs.append(doc)
        return docs

    # Child rows - documents of the child controller

    def _wrap_children(self, only: str | None = None) -> None:
        """The rows of each child table typed ``list[ChildCls]`` in the types block
        as documents of *ChildCls* - each over its row dict, not a copy, so a field
        set on the child is set on the row. The list itself is a new one: whoever
        else holds the old list (a request payload, a returned row) keeps dicts."""
        tables = _child_tables(type(self))
        if not tables:
            return
        data = self.data
        for fieldname, child in tables.items():
            if only is not None and fieldname != only:
                continue
            rows = data.get(fieldname)
            if type(rows) is not list or not rows:
                continue
            dicts = [r for r in rows if isinstance(r, dict)]
            if not dicts:
                continue
            if isinstance(child, str):
                made = iter(document_registry.get(child)._from_rows(dicts, doctype=child))
            else:
                made = iter(child._from_rows(dicts))
            data[fieldname] = [next(made) if isinstance(r, dict) else r for r in rows]

    def _rows(self) -> dict[str, Any]:
        """``self.data`` with child documents as their rows (a shallow copy)."""
        return plain(self.data)

    def _unwrap_children(self) -> None:
        """Child documents in ``self.data`` back to their row dicts - what the
        pipeline below the controller (validation, the store, hooks of other
        apps, the API) reads."""
        if not _child_tables(type(self)):
            return  # _insert / _update take a copy without them (plain) anyway
        data = self.data
        for key, value in data.items():
            if type(value) is list and any(isinstance(v, Document) for v in value):
                data[key] = [row_of(v) for v in value]

    # Attribute routing

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup fails, i.e. for field names. Reserved
        # names land here before __init__ has set them (copy, pickle).
        if name.startswith("_") or name in _RESERVED:
            raise AttributeError(name)
        data = self.data
        if name in data:
            return data[name]
        if name in self._hidden:
            return None
        if self._partial:
            raise AttributeError(
                f"{self.doctype}.{name} was not read: a row of a list holds only the "
                f"fields asked for (fields=[...]) and no child tables"
            )
        # A field not set yet (a new document, an optional field) reads as None;
        # a name that is no field at all is a typo.
        if self._is_field(name):
            return None
        raise AttributeError(f"{self.doctype} has no field {name!r}")

    def _is_field(self, name: str) -> bool:
        """Whether *name* is a field of the DocType: the DocType itself once the
        document has it (fields of other apps and custom fields too), else the
        controller's annotations (its generated type block and mixins). A
        controller without annotations knows no fields - anything goes."""
        dt = self._dt
        if dt is not None:
            return dt.has_field(name)
        known = _annotated_fields(type(self))
        return not known or name in known

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
            if type(value) is list and name in _child_tables(type(self)):
                self._wrap_children(only=name)

    # System fields (read-only)

    def _system(self, fieldname: str, default: Any = None) -> Any:
        data = self.data
        if fieldname in data:
            return data[fieldname]
        if self._partial:  # not read - as for any other field (__getattr__)
            raise AttributeError(fieldname)
        return default

    @property
    def id(self) -> str | None:
        """Same as ``name``."""
        return self._system("name")

    @property
    def name(self) -> str | None:
        return self._system("name")

    @property
    def owner(self) -> str | None:
        return self._system("owner")

    @property
    def idx(self) -> int:
        """Row position in the parent's child table."""
        return self._system("idx", 0)

    @property
    def created_at(self) -> Any:
        return self._system("created_at")

    @property
    def modified_at(self) -> Any:
        return self._system("modified_at")

    @property
    def modified_by(self) -> str | None:
        return self._system("modified_by")

    @property
    def parent(self) -> str | None:
        return self._system("parent")

    @property
    def parentfield(self) -> str | None:
        return self._system("parentfield")

    @property
    def parenttype(self) -> str | None:
        return self._system("parenttype")

    @property
    def grunt(self) -> Any:
        """The ``grunt`` package, so hooks can call ``self.grunt.db...``. Taken from
        ``sys.modules``: it is always loaded first (this is its subpackage), and the
        document layer must not import the facade built on top of it."""
        return sys.modules["grunt"]

    def as_dict(self) -> dict[str, Any]:
        """The document as a JSON object naming its DocType - child rows included."""
        return copy.deepcopy(with_doctype(self.doctype, plain(self.data)))

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
        running under ``user_context(...)``. Whatever can't be resolved stays
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
        return bind(session=self.session, engine=self.engine, user=_user_ctx.get())

    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None:
        unbind(tokens)

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

    def _require_whole(self, action: str) -> None:
        if self._partial:
            raise ValueError(
                f"Cannot {action} {self.doctype} {self.data.get('name')!r}: it is a row of a "
                f"list (only some fields) - read the document with grunt.get_doc() first"
            )

    async def insert(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Run the full create pipeline on this document and return the saved row."""
        self._require_whole("insert")
        original = self.data
        result = await self._insert(ignore_required=ignore_required)
        self._keep(original, result)
        self._wrap_children()
        return result

    async def save(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Run the full update pipeline on this document and return the saved row."""
        self._require_whole("save")
        if self.id is None:
            raise ValueError(f"Cannot save {self.doctype}: document has no name")
        original = self.data
        result = await self._update(self.id, plain(original), ignore_required=ignore_required)
        self._keep(original, result)
        self._wrap_children()
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

    # Reads by class - typed: the IDE knows the fields of what comes back

    @classmethod
    async def get_doc(
        cls,
        name: str | None = None,
        *,
        expand: list[str] | None = None,
        ignore_permissions: bool = False,
    ) -> Self:
        """The document *name* (a singleton needs none) - checks the user's read
        permission, hides the fields they may not see, raises 404 if missing::

            order = await Order.get_doc(order_id)
            order.status = "Closed"
            await order.save()
        """
        return await _api().doc_of(cls, name, expand=expand, ignore_permissions=ignore_permissions)

    @classmethod
    async def find_doc(
        cls, name: str | None = None, *, expand: list[str] | None = None
    ) -> Self | None:
        """Like :meth:`get_doc`, but ``None`` instead of raising 404."""
        return await _api().find_doc_of(cls, name, expand=expand)

    @classmethod
    async def get_list(
        cls,
        *,
        filters: dict[str, Any] | None = None,
        or_filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = 20,
        page: int = 1,
        order_by: str = "modified_at",
        order: str = "desc",
        ignore_permissions: bool = False,
    ) -> list[Self]:
        """Documents the user may read, as rows of this class - permission rules,
        hidden fields and read hooks apply, values as stored::

            for order in await Order.get_list(filters={"status": "Open"}, fields=["name", "total"]):
                order.total

        A row holds only the fields asked for and no child tables: a field it
        lacks raises ``AttributeError``, and it can't be saved - read it with
        :meth:`get_doc` for that. ``grunt.db.get_all(Order, ...)`` reads without
        permissions or hooks.
        """
        return await _api().list_of(
            cls,
            filters=filters,
            or_filters=or_filters,
            fields=fields,
            limit=limit,
            page=page,
            order_by=order_by,
            order=order,
            ignore_permissions=ignore_permissions,
        )

    async def _load_existing(self, doc_id: str | None) -> dict[str, Any]:
        doc = await load_document(self.doctype, doc_id, session=self.session, engine=self.engine)
        return doc.data

    @classmethod
    async def create[**P, T](cls: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """A new document of this controller's DocType, saved - typed like the constructor::

            todo = await ToDo.create(description="Call")
            todo.name

        Checks the caller's ``create`` permission, as ``grunt.new_doc`` does.
        """
        # Typed by the signature; no PEP 695 name in the body (CodeQL reads it as unbound).
        doc: Any = cls(*args, **kwargs)
        await write_guard(doc.doctype, "create")
        await doc.insert()
        return doc

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
            await pipeline.doc_progress(self.doctype, str(doc_id), payload)
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


_DOCUMENT_MRO = frozenset(Document.__mro__)


def _annotated_fields(cls: type) -> frozenset[str]:
    """Names annotated on *cls* and its bases up to :class:`Document` (cached)."""
    cached = cls.__dict__.get("_annotated_fields_cache")
    if cached is not None:
        return cached
    names: set[str] = set()
    for klass in cls.__mro__:
        if klass in _DOCUMENT_MRO:  # Document itself and its framework mixins
            continue
        ann = annotationlib.get_annotations(klass, format=annotationlib.Format.FORWARDREF)
        names.update(n for n in ann if n[:1] != "_")
    known = frozenset(names)
    type.__setattr__(cls, "_annotated_fields_cache", known)
    return known


def _child_tables(cls: type) -> dict[str, Any]:
    """``fieldname -> child controller`` (or its DocType name, when the class is
    only named - ``list["Child"]``, an import under TYPE_CHECKING) for each field
    *cls* annotates ``list[ChildCls]`` (cached)."""
    cached = cls.__dict__.get("_child_tables_cache")
    if cached is not None:
        return cached
    tables: dict[str, Any] = {}
    for klass in reversed(cls.__mro__):
        if klass in _DOCUMENT_MRO:
            continue
        ann = annotationlib.get_annotations(klass, format=annotationlib.Format.FORWARDREF)
        for name, hint in ann.items():
            if name[:1] == "_" or typing.get_origin(hint) is not list:
                continue
            (arg,) = typing.get_args(hint) or (None,)
            if isinstance(arg, type) and issubclass(arg, Document):
                tables[name] = arg
            elif isinstance(arg, str | annotationlib.ForwardRef):
                tables[name] = arg if isinstance(arg, str) else arg.__forward_arg__
    type.__setattr__(cls, "_child_tables_cache", tables)
    return tables


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
        doc._wrap_children()
        try:
            await doc.on_load()
        finally:
            doc._unwrap_children()
    # ``data`` stays rows: the readers by name return it, the update compares with it.
    doc.data = with_doctype(doctype, doc.data)
    return doc


def is_shadowed_field(fieldname: str) -> bool:
    """Whether a controller attribute hides the field - ``doc.user`` is the
    session user, ``doc.delete`` a method - so it is read as ``doc.data[...]``."""
    return fieldname not in SYS_FIELDS and (fieldname in _RESERVED or hasattr(Document, fieldname))
