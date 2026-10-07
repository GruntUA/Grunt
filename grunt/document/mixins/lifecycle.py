"""The document pipeline every controller runs, whatever stores its documents.

Insert, update and delete fire the document events, validate the values,
check permissions and workflow and run the controller's lifecycle hooks; the
storage itself is the controller's: :meth:`load_from_db`, :meth:`db_insert`,
:meth:`db_update`, :meth:`db_delete` and the :meth:`get_list` /
:meth:`get_count` classmethods. ``Document`` keeps its documents in the
DocType's table; a controller for any other source (an API, Redis, files)
subclasses ``BaseDocument`` directly and overrides those.

The ``_``-prefixed methods below the storage contract are the steps a storage
adds to the pipeline - ``Document`` fills them in with its table work (naming
series, child tables, search index, versions).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from grunt import _, log
from grunt.db.errors import friendly_integrity_error
from grunt.document.relations import apply_field_values
from grunt.document.serde import audit_fields, serialize_datetimes, with_doctype
from grunt.document.validation import _validate_data
from grunt.errors import ApplicationError
from grunt.events import fire
from grunt.naming import naming_service
from grunt.naming.patterns import has_counter, parse_pattern
from grunt.permissions.access import RoleAccess
from grunt.permissions.rbac import permission_checker
from grunt.permissions.reference import reference_readable
from grunt.permissions.user_permissions import doc_violation
from grunt.storage.signing import strip_file_signatures
from grunt.webhook.service import webhook_service
from grunt.workflow.engine import _active
from grunt.workflow.guard import check_delete, check_update
from grunt.workflow.registry import get_active_workflow

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from grunt.auth.doctypes.User.user import User
    from grunt.document.base import DocumentList

PROTECTED_FIELDS = frozenset({"name", "owner", "created_at"})


class DocumentLifecycleMixin:
    doctype: str
    data: dict[str, Any]
    user: Any
    session: Any
    engine: Any
    # Set while a pipeline runs: the DocType meta, the values as the caller
    # gave them (on update - only the changes), and (update/delete) the stored
    # document before the change.
    _dt: Any
    input_data: dict[str, Any]
    doc_before_save: dict[str, Any] | None

    #: Why an insert/update/delete the storage doesn't implement is refused
    #: (405) - mark it with ``N_()``; translated when raised.
    not_supported_message: ClassVar[str | None] = None

    def _bind(self) -> None: ...
    def _set_grunt_context(self, user: User) -> tuple: ...  # type: ignore[empty-body]
    @staticmethod
    def _reset_grunt_context(tokens: tuple) -> None: ...

    # Storage

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        """Fill ``self.data`` with the stored document ``self.name``.

        Raise 404 when there is none. *expand* lists the child tables and
        MultiLink fields to load (``None`` - all, ``[]`` - the bare row);
        a storage without them ignores it.
        """
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Virtual DocType “%(doctype)s” has no individual documents")
            % {"doctype": self.doctype},
        )

    async def db_insert(self) -> None:
        """Store the new document ``self.data``.

        May replace ``self.data`` with what was stored (e.g. a generated name).
        """
        raise self._not_supported()

    async def db_update(self) -> None:
        """Store ``self.data`` - the stored document with the changes applied.

        The stored version is ``self.doc_before_save``. May replace ``self.data``.
        """
        raise self._not_supported()

    async def db_delete(self) -> None:
        """Remove the stored document ``self.name``."""
        raise self._not_supported()

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        session: Any,
        user: User,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "modified_at",
        sort_order: str = "desc",
        filters: dict[str, Any] | None = None,
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        """A page of the documents *user* may see. Without storage - none."""
        from grunt.document.base import DocumentList

        return DocumentList(data=[], meta={"total": 0, "page": page, "per_page": per_page})

    @classmethod
    async def get_count(
        cls,
        doctype: str,
        *,
        session: Any,
        user: User,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> int:
        """How many documents *user* may see - by default ``meta.total`` of a list page."""
        result = await cls.get_list(
            doctype, session=session, user=user, page=1, per_page=1, filters=filters, search=search
        )
        return result.meta.get("total") or 0

    def _not_supported(self) -> HTTPException:
        if self.not_supported_message:
            detail = _(self.not_supported_message)
        else:
            detail = _("“%(doctype)s” does not support this operation") % {"doctype": self.doctype}
        return HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail=detail)

    # Pipeline steps of a storage

    def _columns(self, dt: Any) -> set[str] | None:
        """The values a stored row can hold, or ``None`` - any value."""
        return None

    async def _check_can_insert(self, dt: Any) -> None:
        """Refuse an insert the storage can't take (409 for a second singleton row)."""

    async def _insert_instead_of_update(self, dt: Any) -> bool:
        """True when an update must create the document (a singleton saved first)."""
        return False

    async def _before_db_write(self, dt: Any, *, insert: bool) -> None:
        """Last changes to ``self.data`` after the hooks, before it is stored."""

    async def _output(self, dt: Any, *, reload_children: bool) -> dict[str, Any]:
        """The saved document as the API returns it."""
        return with_doctype(self.doctype, serialize_datetimes(dict(self.data)))

    async def _after_insert(self, dt: Any) -> None:
        await webhook_service.fire(self.session, "after_insert", self.doctype, self.data)

    async def _record_update(self, dt: Any, existing: dict[str, Any], result: dict[str, Any]):
        """Keep a record of an update (version, activity diff)."""

    async def _after_update(self, dt: Any, result: dict[str, Any]) -> None:
        await webhook_service.fire(self.session, "after_update", self.doctype, result)

    async def _repoint_references(self, dt: Any, real_id: str, replace_with: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("“%(doctype)s” does not support replacing references")
            % {"doctype": self.doctype},
        )

    async def _after_delete(self, dt: Any, real_id: str, existing: dict[str, Any]) -> None:
        await webhook_service.fire(self.session, "after_delete", self.doctype, existing)

    # Pipeline

    async def _resolve_dt(self, doctype_name: str) -> Any:
        """Return the freshest DocType definition, forcing a lazy reload if needed."""
        import grunt
        from grunt.document.meta import Meta
        from grunt.errors import not_found
        from grunt.metadata.registry import doctype_registry

        fresh = await doctype_registry._lazy_load(doctype_name)
        if fresh is not None:
            return Meta(fresh)
        dt = await grunt.get_meta(doctype_name)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype_name})
        return dt

    async def _run_lifecycle_hooks(self, *hook_names: str) -> None:
        """Call the named controller lifecycle hooks, in order.

        A ``grunt.throw()`` from any hook becomes an HTTP error with the status
        its code maps to - the one place that translates "controller rejected
        the save" into HTTP, shared by insert/update/delete.
        """
        try:
            for hook_name in hook_names:
                await getattr(self, hook_name)()
        except ApplicationError as e:
            raise e.to_api_error() from e

    @staticmethod
    async def _require_user_permissions(dt: Any, row: dict[str, Any], user: User) -> None:
        """403 when the values being written fall outside *user*'s User
        Permissions - the role check alone only looks at the stored row, so
        without this a restricted user could create a record in (or move one
        to) a scope they may not touch."""
        fieldname = await doc_violation(user, dt, row)
        if fieldname is None:
            return
        label = _(dt.get_label(fieldname)) if fieldname else _(dt.doc.label or dt.doc.name)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("No access: “%(field)s” is outside your user permissions") % {"field": label},
        )

    async def _fire_write_hooks(self, primary_event: str, doc: dict[str, Any]) -> None:
        """Fire the two hook events that follow a successful insert/update."""
        for event in (primary_event, "after_save"):
            await fire(event, doctype=self.doctype, doc=doc, user=self.user, session=self.session)

    async def _load_existing(self, doc_id: str | None) -> dict[str, Any]:
        """The stored document *doc_id*, read like ``grunt.get_doc`` reads it."""
        from grunt.document.base import load_document

        doc = await load_document(
            self.doctype, doc_id, session=self.session, engine=self.engine, user=self.user
        )
        return doc.data

    async def _build_initial_row(
        self, dt: Any, data: dict[str, Any], now: datetime
    ) -> dict[str, Any]:
        """The new document: name, audit fields, coerced values and workflow state."""
        user = self.user
        # An explicit caller-supplied name wins over autoname for fixtures and
        # imports, which rely on stable names regardless of the DocType's
        # naming scheme - but NOT for counter-based series (e.g.
        # "ВХ-.YYYY.-.####"), where the counter is the source of truth and
        # must always be consulted. Otherwise any caller (a frontend bug, a
        # crafted API request) could pass an arbitrary `name` and silently
        # hijack the series - the counter would never advance and a later,
        # properly-generated name could collide with it.
        pattern = (dt.autoname or "").removeprefix("format:")
        if data.get("name") and not has_counter(parse_pattern(pattern)):
            doc_name = str(data["name"])
        else:
            custom_autoname: Callable[..., Awaitable[str]] | None = getattr(
                type(self), "autoname", None
            )
            if custom_autoname is not None and callable(custom_autoname):
                doc_name = await custom_autoname(data, self.session)
            else:
                doc_name = await naming_service.generate(dt.autoname or "", data, self.session)

        columns = self._columns(dt)
        row: dict[str, Any] = (
            {}
            if columns is not None
            else {k: v for k, v in data.items() if k[:2] != "__" and k != "doctype"}
        )
        standard: dict[str, Any] = {"name": doc_name, **audit_fields(user.email, now)}
        for k, v in standard.items():
            if columns is None or k in columns:
                row[k] = v

        apply_field_values(dt.fields, data, row)
        # Submitted MultiLink lists, so lifecycle hooks see them (persisted from *data*).
        for f in dt.get_multilink_fields():
            if f.fieldname in data:
                row[f.fieldname] = data[f.fieldname]

        workflow = await get_active_workflow(dt.name)
        if workflow:
            from grunt.workflow.guard import check_create

            await check_create(dt.name, data, user)
            sf = workflow.state_field
            if sf in data:
                row[sf] = data[sf]
            elif sf not in row:
                initial = next((s for s in workflow.states if s.is_initial), None)
                if initial:
                    row[sf] = initial.state
                    target = dt.get_field(initial.update_field or "")
                    if target is not None and target.fieldname not in data:
                        row[target.fieldname] = target.coerce(initial.update_value)

        return row

    def _build_update_payload(self, dt: Any, data: dict[str, Any]) -> dict[str, Any]:
        """The submitted changes to write: coerced, without the protected fields."""
        columns = self._columns(dt)
        update_data: dict[str, Any] = {}
        if columns is None:
            for key, value in data.items():
                if key in PROTECTED_FIELDS or key[:2] == "__" or key == "doctype":
                    continue
                field = dt.get_field(key)
                update_data[key] = field.coerce(value) if field and field.is_physical else value
        else:
            for field in dt.get_physical_fields():
                if field.fieldname not in columns:
                    continue
                if field.fieldname in data and field.fieldname not in PROTECTED_FIELDS:
                    update_data[field.fieldname] = field.coerce(data[field.fieldname])
        now = datetime.now(UTC)
        if columns is None or "modified_at" in columns:
            update_data["modified_at"] = now
        if columns is None or "modified_by" in columns:
            update_data["modified_by"] = self.user.email
        return update_data

    async def _insert(self, *, ignore_required: bool = False) -> dict[str, Any]:
        """Create ``self.data`` as a new document - the insert pipeline.

        The single entry point for creating a document - ``grunt.new_doc``
        calls it too, so global/DocType hooks (notifications, assignment rules,
        backlink sync, activity log) fire identically regardless of the caller.
        """
        self._bind()
        user = self.user
        data = strip_file_signatures(self.data)
        await fire(
            "before_save", doctype=self.doctype, doc=dict(data), user=user, session=self.session
        )

        dt = self._dt = await self._resolve_dt(self.doctype)
        await self._check_can_insert(dt)

        errors = _validate_data(dt, data, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        # A comment / tag / attachment may only be added to a readable document.
        if (
            not RoleAccess(dt, user).is_unrestricted
            and await reference_readable(user, dt, data) is False
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_("No access to the document")
            )

        self.input_data = data
        self.data = await self._build_initial_row(dt, data, datetime.now(UTC))

        tokens = self._set_grunt_context(user)
        try:
            await self._run_lifecycle_hooks("validate", "before_insert", "before_save")
            await self._require_user_permissions(dt, self.data, user)
            await self._before_db_write(dt, insert=True)
            await self.db_insert()
            log.info("document.created", doctype=self.doctype, id=self.data.get("name"))
            await self._run_lifecycle_hooks("after_insert", "after_save")
            await self._after_insert(dt)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc) from exc
        finally:
            self._reset_grunt_context(tokens)

        created = await self._output(dt, reload_children=False)
        self.data = created
        await self._fire_write_hooks("after_insert", created)
        return created

    async def _update(
        self, doc_id: str, data: dict[str, Any], *, ignore_required: bool = False
    ) -> dict[str, Any]:
        """Apply the changes *data* to the stored document *doc_id* - the update pipeline.

        Single entry point for updating a document - see :meth:`_insert`.
        """
        self._bind()
        user = self.user
        data = strip_file_signatures(data)
        # Optimistic-concurrency guard: the `modified_at` the client's edit was
        # based on (sent by offline replays). A newer server copy -> 409.
        base_modified_at = data.pop("__base_modified_at", None)
        dt = self._dt = await self._resolve_dt(self.doctype)

        # A singleton's first save arrives here, not at ``insert`` - the form
        # always routes it as an update (``doc_id`` == DocType name) because
        # there is no separate "new" state. Upsert: if the sole row does not
        # exist yet, create it now (named after the DocType).
        if await self._insert_instead_of_update(dt):
            self.data = {**data, "name": dt.name}
            return await self._insert(ignore_required=ignore_required)

        await fire(
            "before_save",
            doctype=self.doctype,
            doc={"id": doc_id, **data},
            user=user,
            session=self.session,
        )

        existing = await self._load_existing(doc_id)

        # write_guard() (the facade's pre-check) only verifies doctype-level
        # access - it calls permission_checker with doc=None, so a
        # `match`-restricted write permission (e.g. "owner == user") is never
        # evaluated there. `existing` is already fetched for the diff logic
        # below, so this row-level check is free - no extra DB round trip.
        await permission_checker.require(user, dt, "write", existing)

        if (
            base_modified_at
            and existing.get("modified_at") is not None
            and not _same_instant(base_modified_at, existing.get("modified_at"))
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_(
                    "The document was changed after you started editing. "
                    "Open it again and repeat your changes."
                ),
            )

        # Workflow: the state moves only by transitions; an edit may itself be
        # an `on_edit` transition (then *data* carries the new state).
        data = dict(data)
        auto_transition = await check_update(self.doctype, existing, data, user)

        errors = _validate_data(dt, data, partial=True, ignore_required=ignore_required)
        if errors:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

        update_data = self._build_update_payload(dt, data)
        real_id = existing["name"]
        merged = {**existing, **update_data}
        # Inject submitted child-table rows into merged so lifecycle hooks see the
        # incoming data (not the old DB rows) and their mutations are persisted.
        # MultiLink lists too - visible to hooks, persisted from *data*.
        for f in [*dt.get_child_table_fields(), *dt.get_multilink_fields()]:
            if f.fieldname in data:
                merged[f.fieldname] = data[f.fieldname]

        self.input_data = data
        self.doc_before_save = existing
        self.data = merged

        tokens = self._set_grunt_context(user)
        transition_token = _active.set(auto_transition) if auto_transition else None
        try:
            await self._run_lifecycle_hooks("validate", "before_save")
            await self._require_user_permissions(dt, self.data, user)
            await self._before_db_write(dt, insert=False)
            await self.db_update()
            log.info("document.updated", doctype=self.doctype, id=real_id)

            result = await self._output(dt, reload_children=True)
            await self._record_update(dt, existing, result)

            self.data = result
            await self._run_lifecycle_hooks("after_save")

            await self._after_update(dt, result)
            await self._fire_write_hooks("after_update", result)
        except IntegrityError as exc:
            raise friendly_integrity_error(exc, dt.doc) from exc
        finally:
            if transition_token is not None:
                _active.reset(transition_token)
            self._reset_grunt_context(tokens)

        if auto_transition:
            from grunt.workflow.engine import workflow_engine

            await workflow_engine.finish_transition(auto_transition, result, user, self.session)
        return result

    async def _delete(self, *, replace_with: str | None = None) -> None:
        """Delete the stored document ``self.name`` - the delete pipeline.

        Single entry point for deleting a document - see :meth:`_insert`.

        ``replace_with`` - id of a surviving document (same DocType) that every
        reference to the deleted document is repointed to before it is removed.
        """
        self._bind()
        user = self.user
        doc_id = self.data.get("name")
        if doc_id is None:
            raise ValueError(f"Cannot delete {self.doctype}: document has no name")
        dt = self._dt = await self._resolve_dt(self.doctype)

        existing = await self._load_existing(str(doc_id))

        # Same reasoning as update(): write_guard()'s pre-check can't see
        # `match`-restricted delete permissions (doc=None there); this reuses
        # the `existing` fetch already needed below, so it's free.
        await permission_checker.require(user, dt, "delete", existing)

        await check_delete(self.doctype, existing, user)

        real_id = existing["name"]

        if replace_with:
            await self._repoint_references(dt, real_id, replace_with)

        await fire(
            "before_delete", doctype=self.doctype, doc=existing, user=user, session=self.session
        )

        self.doc_before_save = existing
        self.data = existing
        tokens = self._set_grunt_context(user)
        try:
            await self._run_lifecycle_hooks("before_delete")
            await self.db_delete()
            await self._after_delete(dt, real_id, existing)
            await self._run_lifecycle_hooks("after_delete")
        finally:
            self._reset_grunt_context(tokens)

        await fire(
            "after_delete",
            doctype=self.doctype,
            doc_id=real_id,
            doc=existing,
            user=user,
            session=self.session,
        )


def _same_instant(a: Any, b: Any) -> bool:
    """Compare two timestamps given as datetimes or ISO strings (``Z`` / offset / naive-UTC)."""

    def parse(v: Any) -> datetime | None:
        if isinstance(v, datetime):
            dt = v
        elif isinstance(v, str) and v:
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

    pa, pb = parse(a), parse(b)
    return pa is not None and pb is not None and pa == pb
