"""Document CRUD and query API mixin for GruntApp facade."""

import copy
from datetime import UTC, datetime
from typing import Any, overload

from fastapi import HTTPException

import grunt
from grunt import _, log
from grunt.config import settings
from grunt.db.profiler import profile
from grunt.document import collection
from grunt.document.update_side_effects import write_bulk_delete_activity_log
from grunt.errors import forbidden, not_found, unprocessable
from grunt.events import fire
from grunt.local import require_engine, require_session_user
from grunt.naming import naming_service
from grunt.permissions.guards import (
    apply_hidden_fields_to_doc,
    apply_hidden_fields_to_rows,
    doc_guard,
    read_guard,
    write_guard,
)
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import get_roles
from grunt.workflow.engine import workflow_engine
lazy from grunt.cache.document_cache import DocumentCache
lazy from grunt.cache.query_cache import QueryCache
lazy from grunt.db import GruntDB
lazy from grunt.db.api import aggregate_query, list_query
lazy from grunt.document.base import Document, DocumentList, load_document, new_document
lazy from grunt.document.registry import document_registry
lazy from grunt.permissions.query import read_predicate
lazy from grunt.query import run
lazy from grunt.query.aggregates import group_field, parse_aggregation
lazy from grunt.query.nodes import linked_doctypes
lazy from grunt.query.parse import FILTER_OPS
lazy from grunt.query.query import Query
lazy from grunt.query.sql import filter_expr
lazy from grunt.store import AGGREGATE, SQL, supports
lazy from grunt.workflow.registry import get_active_workflow


class DocumentAPI:
    """Document CRUD, list/query, and workflow helpers for GruntApp.

    Guard/identity logic is imported as module-level functions from
    :mod:`grunt.local` and :mod:`grunt.permissions.guards`; the annotations
    below declare the ``db``/``query_cache`` attributes provided by the composed
    :class:`~grunt.app.GruntApp` so type checkers can resolve them.
    """

    db: GruntDB
    query_cache: QueryCache
    doc_cache: DocumentCache

    def _is_read_only_doctype(self, dt: Any) -> bool:
        """True when DocType has explicit permissions and none allow mutation."""
        perms = getattr(dt, "permissions", []) or []
        if not perms:
            return False
        for p in perms:
            if any(
                (
                    bool(getattr(p, "write", False)),
                    bool(getattr(p, "create", False)),
                    bool(getattr(p, "delete", False)),
                )
            ):
                return False
        return True

    @staticmethod
    async def _access_key(dt: Any, user: Any) -> str | None:
        """What the user may see of *dt*, as part of a query-cache key: their
        roles (hidden fields) and their row predicate (``match``, User
        Permissions). A change to either is a different key, so a revoked role
        or tightened rule never serves the wider cached result.

        ``None`` - not cacheable: the predicate reads other DocTypes (shares,
        inherited or child access), whose changes don't invalidate this cache.
        """
        predicate = await read_predicate(user, dt)
        if linked_doctypes(predicate):
            return None
        roles = sorted(await get_roles(user))
        return repr((roles, predicate))

    async def _invalidate_list_cache(
        self, doctype: str, names: str | list[str] | None = None
    ) -> None:
        cache = getattr(self, "query_cache", None)
        if cache is not None:
            try:
                await cache.invalidate_doctype(doctype)
            except Exception as exc:
                log.warning("query_cache.invalidate_failed", doctype=doctype, error=str(exc))

        doc_cache = getattr(self, "doc_cache", None)
        if doc_cache is None:
            return
        try:
            if names is None:
                await doc_cache.invalidate_doctype(doctype)
            else:
                for name in [names] if isinstance(names, str) else names:
                    await doc_cache.invalidate(doctype, name)
        except Exception as exc:
            log.warning("doc_cache.invalidate_failed", doctype=doctype, error=str(exc))

    async def _load(
        self, doctype: str, id_or_name: str | None, user: Any, expand: list[str] | None = None
    ) -> Document:

        return await load_document(
            doctype,
            id_or_name,
            expand=expand,
            session=grunt.get_session(),
            engine=require_engine(),
        )

    async def _new(self, doctype: str, data: dict[str, Any], user: Any) -> Document:

        return await new_document(
            doctype, data, session=grunt.get_session(), engine=require_engine()
        )

    @overload
    async def get_doc(
        self,
        doctype: str,
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> dict[str, Any]: ...

    @overload
    async def get_doc[D: Document](
        self,
        doctype: type[D],
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> D: ...

    @overload
    async def get_doc(self, doctype: dict[str, Any]) -> Document: ...

    @profile("grunt.get_doc")
    async def get_doc(self, doctype, id_or_name=None, *, expand=None):
        """Fetch a single document by id or name.

        Pass a doctype name for the untyped dict result, or a ``Document``
        subclass for a typed controller instance (mirrors ``grunt.get_all``)::

            order = await grunt.get_doc(Order, order_id)    # typed -> Order
            order = await grunt.get_doc("Order", order_id)  # dict

        For a singleton DocType the id is optional - there is only one row::

            settings = await grunt.get_doc("SystemSettings")

        A document's JSON (its ``"doctype"`` key names the DocType, child rows
        included) gives a new, unsaved controller - the caller's ``create``
        permission is checked here::

            todo = await grunt.get_doc({"doctype": "ToDo", "description": "Call"})
            await todo.insert()
        """
        if isinstance(doctype, dict):
            target = doctype.get("doctype")
            if not isinstance(target, str) or not target:
                raise ValueError("Document JSON has no 'doctype'")
            _dt, user, _session = await write_guard(target, "create")
            return await self._new(target, copy.deepcopy(doctype), user)

        if isinstance(doctype, type):
            name: str = getattr(doctype, "doctype", doctype.__name__)
            dt, user, hidden_fields = await read_guard(name)
            await fire("before_read", doctype=name, user=user, doc_id=id_or_name)
            data = (await self._load(name, id_or_name, user, expand)).data
            await permission_checker.require(dt, "read", data, user=user)
            data = apply_hidden_fields_to_doc(data, hidden_fields)
            await fire("after_read", doctype=name, user=user, doc=data)
            # The registered controller, when it extends the class asked for
            # (doctype_mixins / override_doctype_class of other apps).
            controller = document_registry.get(name)
            cls = controller if issubclass(controller, doctype) else doctype
            return cls(doctype=name, data=data, session=grunt.get_session())

        dt, user, hidden_fields = await read_guard(doctype)
        await fire("before_read", doctype=doctype, user=user, doc_id=id_or_name)
        doc = (await self._load(doctype, id_or_name, user, expand)).data
        await permission_checker.require(dt, "read", doc, user=user)
        doc = apply_hidden_fields_to_doc(doc, hidden_fields)
        await fire("after_read", doctype=doctype, user=user, doc=doc)
        return doc

    @overload
    async def find_doc(
        self,
        doctype: str,
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> dict[str, Any] | None: ...

    @overload
    async def find_doc[D: Document](
        self,
        doctype: type[D],
        id_or_name: str | None = None,
        *,
        expand: list[str] | None = None,
    ) -> D | None: ...

    async def find_doc(self, doctype, id_or_name=None, *, expand=None):
        """Like :meth:`get_doc`, but returns ``None`` instead of raising 404."""

        try:
            if isinstance(doctype, type):
                return await self.get_doc(doctype, id_or_name, expand=expand)
            return await self.get_doc(doctype, id_or_name, expand=expand)
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    async def get_doc_instance(self, doctype: str, id_or_name: str) -> Document:
        """Fetch a document and return it as an instantiated controller."""
        dt, user, hidden_fields = await read_guard(doctype)
        doc = await self._load(doctype, id_or_name, user)
        await permission_checker.require(dt, "read", doc.data, user=user)
        doc.data = apply_hidden_fields_to_doc(doc.data, hidden_fields)
        return doc

    async def new_doc(
        self,
        doctype: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Create a new document and return it.

        Lifecycle hooks (notifications, assignment rules, backlink sync, activity
        log) fire inside the insert pipeline itself, so they run identically here
        and via ``Document.insert()`` - see ``DocumentLifecycleMixin._insert``.
        """
        _dt, user, _session = await write_guard(doctype, "create")
        doc = await self._new(doctype, dict(data), user)
        created = await doc._insert(ignore_required=ignore_required)
        await self._invalidate_list_cache(doctype, created.get("name"))
        try:
            _, _, hidden_fields = await read_guard(doctype)
        except HTTPException:
            # A role granted "create" but no "read" at all (e.g. a public
            # WebForm's Guest - create-only by design, so anonymous submitters
            # can't list or re-read other people's submissions) still gets its
            # own just-created document back: create permission is already the
            # trust boundary here, and there is no read-permission rule to mask
            # fields against for a role that holds none.
            hidden_fields = frozenset()
        return apply_hidden_fields_to_doc(created, hidden_fields)

    async def save_doc(
        self,
        doctype: str,
        id_or_name: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Update an existing document and return the updated version.

        See :meth:`new_doc` - lifecycle hooks fire inside the update pipeline.
        """
        _dt, user, _session = await write_guard(doctype, "write")
        doc = await self._new(doctype, {}, user)
        updated = await doc._update(id_or_name, data, ignore_required=ignore_required)
        await self._invalidate_list_cache(doctype, id_or_name)
        _, _, hidden_fields = await read_guard(doctype)
        return apply_hidden_fields_to_doc(updated, hidden_fields)

    async def delete_doc(
        self, doctype: str, id_or_name: str, replace_with: str | None = None
    ) -> None:
        """Delete a document.

        See :meth:`new_doc` - lifecycle hooks fire inside the delete pipeline.

        ``replace_with`` repoints every reference to the deleted document at
        this surviving document of the same DocType before removal.
        """
        _dt, user, _session = await write_guard(doctype, "delete")
        doc = await self._new(doctype, {"name": id_or_name}, user)
        await doc._delete(replace_with=replace_with)
        await self._invalidate_list_cache(doctype, id_or_name)

    async def rename_doc(self, doctype: str, old_id: str, new_id: str) -> dict[str, Any]:
        """Rename a document and cascade all references."""
        dt, user, session = await write_guard(doctype, "write")
        await fire(
            "before_rename",
            doctype=doctype,
            old_id=old_id,
            new_id=new_id,
            user=user,
            session=session,
        )

        res = await collection.rename_document(
            grunt.get_session(), require_engine(), doctype, old_id, new_id, user
        )

        await fire(
            "after_rename",
            doctype=doctype,
            old_id=old_id,
            new_id=new_id,
            doc=res,
            user=user,
            session=session,
        )
        await self._invalidate_list_cache(doctype, [old_id, new_id])
        return res

    async def bulk_delete_docs(
        self,
        doctype: str,
        ids: list[str],
        *,
        replace_with: str | None = None,
        progress_cb: Any | None = None,
    ) -> tuple[int, list[str]]:
        """Delete multiple documents efficiently with a single batch transaction.

        Uses the optimised ``collection.bulk_delete`` path:
        - 1 SELECT to fetch all candidates
        - Per-document ``before_delete`` / ``after_delete`` controller hooks
        - 1 batch DELETE statement
        - 1 batch MultiLink cleanup
        - 1 batch search-index removal
        - 1 batch ActivityLog INSERT (instead of N individual writes)

        Returns ``(deleted_count, errors)`` where ``errors`` items are
        formatted as ``"<doc_id>: <message>"``.
        """
        if not ids:
            return 0, []

        _dt, user, session = await write_guard(doctype, "delete")
        engine = require_engine()

        deleted, errors = await collection.bulk_delete(
            session,
            engine,
            doctype,
            ids,
            user,
            replace_with=replace_with,
            progress_cb=progress_cb,
        )

        if deleted > 0:
            # Compute the IDs that were actually deleted (ids - failed)
            failed_ids: set[str] = {e.split(":")[0].strip() for e in errors}
            deleted_ids = [i for i in ids if i not in failed_ids]
            await write_bulk_delete_activity_log(
                session=session,
                doctype_name=doctype,
                doc_ids=deleted_ids,
                user_email=user,
            )

        await self._invalidate_list_cache(doctype, ids)
        return deleted, errors

    @profile("grunt.get_list")
    async def get_list(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        page: int = 1,
        order_by: str = "modified_at",
        order: str = "desc",
        search: str | None = None,
        cursor: str | None = None,
        include_total: bool = True,
    ) -> DocumentList:
        """Fetch a guarded, field-masked page of documents (with pagination meta).

        The single read entry point: applies read_guard, before/after_read hooks
        and hidden-field masking. Returns a :class:`DocumentList` whose
        ``to_dict()`` carries pagination metadata.

        ``include_total=False`` skips the pagination ``COUNT(*)`` query for
        call sites that never read ``meta.total`` (e.g. sidebar widgets).
        """
        dt, user, hidden_fields = await read_guard(doctype)
        await fire(
            "before_read",
            doctype=doctype,
            user=user,
            filters=filters,
            fields=fields,
            limit=limit,
            page=page,
            order_by=order_by,
            order=order,
            search=search,
        )

        result = None
        # Only rows that change through create/update/delete - the paths that
        # invalidate this cache (_invalidate_list_cache) - are cached: a store
        # outside SQL (ring buffer, external API, ...) changes on its own, and a
        # cached snapshot of it could go stale forever.
        cache_eligible = (
            settings.query_cache_enabled and supports(dt, SQL) and self._is_read_only_doctype(dt)
        )
        cache = getattr(self, "query_cache", None)
        cache_key: str | None = None

        # Keyset (cursor) pages are not cached - the cursor already scopes them.
        access = (
            await self._access_key(dt, user)
            if cache_eligible and cache is not None and cursor is None
            else None
        )
        if access is not None and cache is not None:
            cache_key = cache.build_key(
                doctype=doctype,
                user_email=user,
                access=access,
                filters=filters,
                fields=fields,
                limit=limit,
                page=page,
                order_by=order_by,
                order=order,
                search=search,
                include_total=include_total,
            )
            result = await cache.get_list(cache_key)

        if result is None:
            result = await collection.list_documents(
                grunt.get_session(),
                doctype,
                user,
                page=page,
                per_page=limit,
                sort_by=order_by,
                sort_order=order,
                filters=filters,
                search=search,
                fields=fields,
                cursor=cursor,
                include_total=include_total,
            )
            if cache_key and cache is not None:
                await cache.set_list(cache_key, result)
        else:
            # Protect cached object from accidental in-request mutation.
            result = copy.deepcopy(result)

        apply_hidden_fields_to_rows(result, hidden_fields)
        await fire("after_read", doctype=doctype, user=user, data=result)
        return result

    @profile("grunt.get_all")
    async def get_all[T](
        self,
        model_class: type[T],
        *,
        filters: dict[str, Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        page: int = 1,
        order_by: str = "modified_at",
        order: str = "desc",
        search: str | None = None,
    ) -> list[T]:
        """Fetch a list of documents and return them as instantiated controllers.

        This method supports typed results using Python generics::

            users = await grunt.get_all(User, filters={"active": True})
        """

        doctype: str = getattr(model_class, "doctype", model_class.__name__)
        dt, user, hidden_fields = await read_guard(doctype)

        offset = max(page - 1, 0) * limit
        await fire(
            "before_read",
            doctype=doctype,
            user=user,
            filters=filters,
            fields=fields,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order=order,
            search=search,
            method="get_all",
        )

        # Same row-level gate get_list applies (match rules, User Permissions,
        # shares). Without it get_all would return every row the doctype-level
        # read grant allows, ignoring `match`.
        query = list_query(
            dt,
            filters=filters,
            fields=fields,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order=order,
        )
        rows = await run.fetch(query, user=user)
        apply_hidden_fields_to_rows(rows, hidden_fields)
        await fire("after_read", doctype=doctype, user=user, data=rows, method="get_all")

        session = grunt.get_session()
        controllers = [
            model_class(doctype=doctype, data=row, session=session)  # type: ignore[return-value]
            for row in rows
        ]
        return DocumentList(controllers, meta=getattr(rows, "meta", {}))

    async def bulk_insert(
        self,
        doctype: str,
        records: list[dict[str, Any]],
    ) -> list[str]:
        """Create multiple documents in a single database round-trip."""
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        table = dt.table
        user = require_session_user()
        session = grunt.get_session()

        now = datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        names: list[str] = []

        for rec in records:
            doc_name = await naming_service.generate(dt.autoname or "", rec, session)
            names.append(doc_name)
            row = {k: v for k, v in rec.items() if k in table.c}
            standard = {
                "name": doc_name,
                "owner": user,
                "created_at": now,
                "modified_at": now,
                "modified_by": user,
            }
            for k, v in standard.items():
                if k in table.c:
                    row[k] = v
            rows.append(row)

        await self.db.insert_many(doctype, rows)
        log.info("grunt.bulk_insert", doctype=doctype, count=len(rows))
        await self._invalidate_list_cache(doctype)
        return names

    async def bulk_update(
        self,
        doctype: str,
        filters: dict[str, Any],
        values: dict[str, Any],
    ) -> int:
        """Update multiple documents matching ``filters`` in a single query."""
        user = require_session_user()

        update_values = dict(values)
        update_values["modified_at"] = datetime.now(UTC)
        update_values["modified_by"] = user

        row_count = await self.db.bulk_update(doctype, filters, update_values)
        log.info("grunt.bulk_update", doctype=doctype, rows=row_count)
        await self._invalidate_list_cache(doctype)
        return row_count

    @profile("grunt.count")
    async def count(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        respect_permissions: bool = False,
    ) -> int:
        """Count documents matching optional filters.

        By default this is a raw table count (no permission check) - many
        internal callers (bootstrap, formulas, background jobs) rely on that.
        Pass ``respect_permissions=True`` to apply the same row-level ``match``
        filter ``grunt.get_list`` uses, so the number never includes rows the
        list view would hide. The internal system context sees the full count
        either way.

        Permission-aware counts are cached per (doctype, user, filters) - cheap
        to keep fresh because every create/update/delete already invalidates
        the doctype's cache entries (see ``_invalidate_list_cache``), so the
        TTL only covers the gap until that invalidation lands (e.g. a write
        made outside the ORM, or a Redis hiccup), not routine staleness.
        """
        if not respect_permissions:
            return await self.db.count(doctype, filters=filters)

        user = require_session_user()
        cache = getattr(self, "query_cache", None)
        cache_key: str | None = None
        # A store outside SQL changes outside the pipeline - never cached.
        dt = await grunt.get_meta(doctype)
        access = (
            await self._access_key(dt, user)
            if settings.query_cache_enabled and cache is not None and dt and supports(dt, SQL)
            else None
        )
        if access is not None and cache is not None:
            cache_key = cache.build_count_key(
                doctype=doctype,
                user_email=user,
                access=access,
                filters=filters,
            )
            cached = await cache.get_count(cache_key)
            if cached is not None:
                return cached

        result = await collection.count_documents(
            grunt.get_session(), doctype, user, filters=filters
        )
        if cache_key is not None and cache is not None:
            await cache.set_count(cache_key, result)
        return result

    @profile("grunt.aggregate")
    async def aggregate(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | list[str] | None = None,
        aggregations: dict[str, str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        """GROUP BY / SUM / COUNT over the rows the current user may read.

        Same arguments as ``grunt.db.aggregate``, but read permission, row-level
        ``match`` rules and shares apply, and permission-hidden fields can be
        neither grouped, aggregated nor filtered on. Without ``aggregations``
        each group gets a ``count``::

            rows = await grunt.aggregate(
                "Invoice",
                filters={"status": "Paid"},
                group_by="month(posting_date)",
                aggregations={"total": "sum(amount)", "n": "count()"},
            )
        """

        dt, user, hidden = await read_guard(doctype)
        if not supports(dt, AGGREGATE):
            raise unprocessable(_("“%(doctype)s” has no table to aggregate") % {"doctype": doctype})

        group_by = [group_by] if isinstance(group_by, str) else list(group_by or [])
        aggregations = aggregations or {"count": "count()"}
        referenced: set[str] = set()
        for gb in group_by:
            referenced.add(group_field(gb))
        for expr in (aggregations or {}).values():
            try:
                field = parse_aggregation(expr)[1]
            except ValueError as e:
                raise unprocessable(str(e)) from None
            if field and field != "*":
                referenced.add(field)
        for key in filters or {}:
            field, _sep, op = key.rpartition("__")
            referenced.add(field if field and op in FILTER_OPS else key)

        columns = dt.columns
        unknown = sorted(referenced - columns)
        if unknown:
            raise unprocessable(_("Unknown fields: %(fields)s") % {"fields": ", ".join(unknown)})
        if referenced & hidden:
            raise forbidden(
                _("Not permitted to use fields: %(fields)s")
                % {"fields": ", ".join(sorted(referenced & hidden))}
            )

        await fire("before_read", doctype=doctype, user=user, filters=filters, method="aggregate")
        query = aggregate_query(
            dt,
            filters=filters,
            group_by=group_by,
            aggregations=aggregations,
            limit=limit,
            order_by=order_by,
            order=order,
        )
        try:
            rows = await run.aggregate(query, user=user)
        except ValueError as e:
            raise unprocessable(str(e)) from None
        await fire("after_read", doctype=doctype, user=user, data=rows, method="aggregate")
        return rows

    async def exists(
        self,
        doctype: str,
        filters: dict[str, Any] | str,
    ) -> str | None:
        """Return the document id if a matching record exists, otherwise ``None``.

        Unlike ``grunt.db.exists``, this respects the current user's read
        permission - row-level rules and hidden fields included::

            if await grunt.exists("Invoice", {"number": "INV-001", "status": "Unpaid"}):
                ...
        """
        dt, user, _hidden = await read_guard(doctype)
        await fire("before_read", doctype=doctype, user=user, filters=filters, method="exists")
        # The list's read path: row-level rules apply, a hidden field can't be
        # probed by filtering on it.
        query = Query(
            dt.name, where=filter_expr(filters, dt.columns, dt), fields=("name",), limit=1
        )
        rows = await run.fetch(query, user=user)
        exists = rows[0]["name"] if rows else None
        await fire(
            "after_read",
            doctype=doctype,
            user=user,
            data={"exists": exists},
            method="exists",
        )
        return exists

    async def get_value(
        self,
        doctype: str,
        id_or_name: str,
        fieldname: str,
    ) -> Any:
        """Fetch a single field value from a document.

        Checks read permission on that very document (role ``match`` rules,
        shares, User Permissions) and raises ``403`` if the user has no access
        or asks for a field hidden from them::

            status = await grunt.get_value("Invoice", invoice_id, "status")
        """
        _dt, user, hidden = await read_guard(doctype)
        await doc_guard(doctype, id_or_name, "read")
        asked = {fieldname} if isinstance(fieldname, str) else set(fieldname)
        if asked & hidden:
            raise forbidden(
                _("Not permitted to use fields: %(fields)s")
                % {"fields": ", ".join(sorted(asked & hidden))}
            )
        await fire(
            "before_read",
            doctype=doctype,
            user=user,
            doc_id=id_or_name,
            fieldname=fieldname,
            method="get_value",
        )
        value = await self.db.get_value(doctype, id_or_name, fieldname)
        await fire(
            "after_read",
            doctype=doctype,
            user=user,
            data={"fieldname": fieldname, "value": value},
            method="get_value",
        )
        if isinstance(value, dict):  # fieldname "*" - the whole row
            value = apply_hidden_fields_to_doc(value, hidden)
        return value

    async def set_value(
        self,
        doctype: str,
        id_or_name: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None:
        """Update one or more fields directly - lightweight, no lifecycle hooks.

        Checks write permission on that very document (and that no field hidden
        from the user is set), then issues a single SQL UPDATE.
        Use :meth:`save_doc` when you need ``before_save``/``after_save`` hooks
        to run (e.g. validation, audit log)::

            # single field
            await grunt.set_value("Invoice", invoice_id, "status", "Paid")

            # multiple fields at once
            await grunt.set_value("Invoice", invoice_id, {"status": "Paid", "paid_at": now})
        """
        dt, user, _session = await write_guard(doctype, "write")
        await doc_guard(doctype, id_or_name, "write")
        names = set(fieldname) if isinstance(fieldname, dict) else {fieldname}
        hidden = names & (await permission_checker.hidden_fields(dt, user=user))
        if hidden:
            raise forbidden(
                _("Not permitted to change fields: %(fields)s")
                % {"fields": ", ".join(sorted(dt.get_label(f) for f in hidden))}
            )
        await self.db.set_value(doctype, id_or_name, fieldname, value)
        await self._invalidate_list_cache(doctype, id_or_name)

    async def get_single(self, doctype: str, fieldname: str) -> Any:
        """Fetch a field value from a Single DocType (singleton document).

        Single DocTypes hold global settings and have no id - they are stored
        as key/value rows rather than regular documents::

            currency = await grunt.get_single("SystemSettings", "default_currency")
        """
        return await self.db.get_single_value(doctype, fieldname)

    async def submit(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply a workflow transition to a document.

        ``action`` must match a transition label defined in the DocType's workflow.
        Raises ``HTTPException(409)`` if the transition is not available for the
        current document state or the user lacks the required role::

            await grunt.submit("LeaveRequest", request_id, "Approve")

        ``values`` fills in the transition's ``prompt_fields`` (e.g. a note
        collected in a dialog before applying the transition).
        """
        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
        return await workflow_engine.apply_transition(
            dt.doc,
            doc_id,
            action,
            require_session_user(),
            grunt.get_session(),
            require_engine(),
            values,
        )

    async def copy_doc(
        self,
        doctype: str,
        id_or_name: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a copy of a document and return it.

        Copies every field except ``id`` / ``name`` / ``created_at`` (child
        tables included), then inserts a fresh document. The workflow state
        and the fields its states set aren't copied - the copy starts in the
        initial state. Pass ``overrides`` to change specific fields on the copy::

            draft = await grunt.copy_doc("Invoice", original_id, overrides={"status": "Draft"})
        """
        original = await self.get_doc(doctype, id_or_name)
        skip = {"id", "name", "created_at"}
        workflow = await get_active_workflow(doctype)
        if workflow:
            skip.add(workflow.state_field)
            skip.update(s.update_field for s in workflow.states if s.update_field)
        data = {k: v for k, v in original.items() if k not in skip}
        if overrides:
            data.update(overrides)
        return await self.new_doc(doctype, data)
