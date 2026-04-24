"""Document CRUD and query API mixin for GruntApp facade."""

from __future__ import annotations

import copy
from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog

from grunt.config import settings
from grunt.core.db.profiler import profile
from grunt.core.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from grunt.core.doctypes.user.user import User
    from grunt.core.document.base import Document

logger = structlog.get_logger()


class DocumentAPI:
    """Document CRUD, list/query, and workflow helpers for GruntApp."""

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
                    bool(getattr(p, "submit", False)),
                )
            ):
                return False
        return True

    async def _invalidate_list_cache(self, doctype: str) -> None:
        cache = getattr(self, "query_cache", None)
        if cache is None:
            return
        try:
            await cache.invalidate_doctype(doctype)
        except Exception as exc:  # noqa: BLE001
            logger.warning("query_cache.invalidate_failed", doctype=doctype, error=str(exc))

    def _svc(self):
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        return DocumentService(self._require_session(), self._require_engine())

    @profile("grunt.get_doc")
    async def get_doc(
        self,
        doctype: str,
        id_or_name: str,
        *,
        expand: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch a single document by id or name."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, hidden_fields = await self._read_guard(doctype)
        await fire("before_read", doctype=doctype, user=user, doc_id=id_or_name)
        doc = await self._svc().get_document(doctype, id_or_name, user, expand=expand)
        doc = self._apply_hidden_fields_to_doc(doc, hidden_fields)
        await fire("after_read", doctype=doctype, user=user, doc=doc)
        return doc

    async def get_doc_instance(self, doctype: str, id_or_name: str) -> "Document":
        """Fetch a document and return it as an instantiated controller."""
        from grunt.core.document.registry import document_registry  # noqa: PLC0415

        dt, user, hidden_fields = await self._read_guard(doctype)
        data = await self._svc().get_document(doctype, id_or_name, user)
        data = self._apply_hidden_fields_to_doc(data, hidden_fields)
        controller_cls = document_registry.get(doctype)
        return controller_cls(doctype, data, user, self._require_session())

    async def new_doc(
        self,
        doctype: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Create a new document and return it."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, session = await self._write_guard(doctype, "create")
        await fire("before_save", doctype=doctype, doc=dict(data), user=user, session=session)
        created = await self._svc().create_document(
            doctype, data, user, ignore_required=ignore_required
        )
        await fire("after_insert", doctype=doctype, doc=created, user=user, session=session)
        await fire("after_save", doctype=doctype, doc=created, user=user, session=session)
        await self._invalidate_list_cache(doctype)
        _, _, hidden_fields = await self._read_guard(doctype)
        return self._apply_hidden_fields_to_doc(created, hidden_fields)

    async def save_doc(
        self,
        doctype: str,
        id_or_name: str,
        data: dict[str, Any],
        *,
        ignore_required: bool = False,
    ) -> dict[str, Any]:
        """Update an existing document and return the updated version."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, session = await self._write_guard(doctype, "write")
        await fire(
            "before_save",
            doctype=doctype,
            doc={"id": id_or_name, **data},
            user=user,
            session=session,
        )
        updated = await self._svc().update_document(
            doctype, id_or_name, data, user, ignore_required=ignore_required
        )
        await fire("after_update", doctype=doctype, doc=updated, user=user, session=session)
        await fire("after_save", doctype=doctype, doc=updated, user=user, session=session)
        await self._invalidate_list_cache(doctype)
        _, _, hidden_fields = await self._read_guard(doctype)
        return self._apply_hidden_fields_to_doc(updated, hidden_fields)

    async def delete_doc(self, doctype: str, id_or_name: str) -> None:
        """Delete a document."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, session = await self._write_guard(doctype, "delete")

        snapshot: dict[str, Any] | None = None
        try:
            snapshot = await self._svc().get_document(doctype, id_or_name, user)
        except Exception:  # noqa: BLE001
            snapshot = {"id": id_or_name}

        await fire("before_delete", doctype=doctype, doc=snapshot, user=user, session=session)
        await self._svc().delete_document(doctype, id_or_name, user)
        await fire(
            "after_delete",
            doctype=doctype,
            doc_id=snapshot.get("id", id_or_name),
            doc=snapshot,
            user=user,
            session=session,
        )
        await self._invalidate_list_cache(doctype)

    async def rename_doc(self, doctype: str, old_id: str, new_id: str) -> dict[str, Any]:
        """Rename a document and cascade all references."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, session = await self._write_guard(doctype, "write")
        await fire(
            "before_rename",
            doctype=doctype,
            old_id=old_id,
            new_id=new_id,
            user=user,
            session=session,
        )

        res = await self._svc().rename_document(doctype, old_id, new_id, user)

        await fire(
            "after_rename",
            doctype=doctype,
            old_id=old_id,
            new_id=new_id,
            doc=res,
            user=user,
            session=session,
        )
        await self._invalidate_list_cache(doctype)
        return res

    async def bulk_delete_docs(
        self,
        doctype: str,
        ids: list[str],
        *,
        progress_cb: Any | None = None,
    ) -> tuple[int, list[str]]:
        """Delete multiple documents through high-level API with hooks/permissions.

        Returns ``(deleted_count, errors)`` where ``errors`` items are
        formatted as ``"<doc_id>: <message>"``.
        """
        if not ids:
            return 0, []

        deleted = 0
        errors: list[str] = []
        total = len(ids)

        async def _report(done: int) -> None:
            if progress_cb is not None:
                await progress_cb(done, total, len(errors))

        for idx, doc_id in enumerate(ids, start=1):
            try:
                await self.delete_doc(doctype, doc_id)
                deleted += 1
            except Exception as e:  # noqa: BLE001
                detail = getattr(e, "detail", str(e))
                errors.append(f"{doc_id}: {detail}")
            await _report(idx)

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
    ) -> list[dict[str, Any]]:
        """Fetch a list of documents as dictionaries."""
        from grunt.core.hooks import fire  # noqa: PLC0415

        dt, user, hidden_fields = await self._read_guard(doctype)
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
        cache_eligible = settings.query_cache_enabled and self._is_read_only_doctype(dt)
        cache = getattr(self, "query_cache", None)
        cache_key: str | None = None

        if cache_eligible and cache is not None:
            cache_key = cache.build_key(
                doctype=doctype,
                user_email=getattr(user, "email", ""),
                filters=filters,
                fields=fields,
                limit=limit,
                page=page,
                order_by=order_by,
                order=order,
                search=search,
            )
            result = await cache.get_list(cache_key)

        if result is None:
            result = await self._svc().list_documents(
                doctype,
                user,
                page=page,
                per_page=limit,
                sort_by=order_by,
                sort_order=order,
                filters=filters,
                search=search,
                fields=fields,
            )
            if cache_key and cache is not None:
                await cache.set_list(cache_key, result)
        else:
            # Protect cached object from accidental in-request mutation.
            result = copy.deepcopy(result)

        self._apply_hidden_fields_to_rows(result, hidden_fields)
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
        from grunt.core.document.base import DocumentList  # noqa: PLC0415
        from grunt.core.hooks import fire  # noqa: PLC0415

        doctype: str = getattr(model_class, "doctype", model_class.__name__)
        _, user, hidden_fields = await self._read_guard(doctype)

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

        rows = await self.db.get_all(
            doctype,
            filters=filters,
            fields=fields,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order=order,
        )
        self._apply_hidden_fields_to_rows(rows, hidden_fields)
        await fire("after_read", doctype=doctype, user=user, data=rows, method="get_all")

        session = self._require_session()
        controllers = [
            model_class(doctype=doctype, data=row, user=user, session=session)  # type: ignore[return-value, call-arg]
            for row in rows
        ]
        return DocumentList(controllers, meta=getattr(rows, "meta", {}))

    async def bulk_insert(
        self,
        doctype: str,
        records: list[dict[str, Any]],
    ) -> list[str]:
        """Create multiple documents in a single database round-trip."""
        import uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        table = compile_doctype_to_table(dt)
        user = self._require_user()

        now = datetime.now(UTC)
        rows: list[dict[str, Any]] = []
        ids: list[str] = []

        for rec in records:
            doc_id = str(uuid.uuid4())
            ids.append(doc_id)
            row = {k: v for k, v in rec.items() if k in table.c}
            standard = {
                "id": doc_id,
                "name": rec.get("name") or doc_id,
                "owner": user.email,
                "created_at": now,
                "modified_at": now,
                "modified_by": user.email,
                "docstatus": 0,
            }
            for k, v in standard.items():
                if k in table.c:
                    row[k] = v
            rows.append(row)

        await self.db.insert_many(doctype, rows)
        logger.info("grunt.bulk_insert", doctype=doctype, count=len(rows))
        await self._invalidate_list_cache(doctype)
        return ids

    async def bulk_update(
        self,
        doctype: str,
        filters: dict[str, Any],
        values: dict[str, Any],
    ) -> int:
        """Update multiple documents matching ``filters`` in a single query."""
        from datetime import datetime  # noqa: PLC0415
        user = self._require_user()

        update_values = dict(values)
        update_values["modified_at"] = datetime.now(UTC).isoformat()
        update_values["modified_by"] = user.email

        row_count = await self.db.bulk_update(doctype, filters, update_values)
        logger.info("grunt.bulk_update", doctype=doctype, rows=row_count)
        await self._invalidate_list_cache(doctype)
        return row_count

    @profile("grunt.count")
    async def count(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Count documents matching optional filters."""
        return await self.db.count(doctype, filters=filters)

    async def exists(
        self,
        doctype: str,
        filters: dict[str, Any] | str,
    ) -> str | None:
        """Return the document id if a matching record exists, otherwise ``None``.

        Unlike ``grunt.db.exists``, this respects the current user's read permission::

            if await grunt.exists("Invoice", {"number": "INV-001", "status": "Unpaid"}):
                ...
        """
        from grunt.core.hooks import fire  # noqa: PLC0415

        _, user, _ = await self._read_guard(doctype)
        await fire("before_read", doctype=doctype, user=user, filters=filters, method="exists")
        exists = await self.db.exists(doctype, filters)
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

        Checks read permission and raises ``403`` if the user has no access::

            status = await grunt.get_value("Invoice", invoice_id, "status")
        """
        from grunt.core.hooks import fire  # noqa: PLC0415

        _, user, _ = await self._read_guard(doctype)
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
        return value

    async def set_value(
        self,
        doctype: str,
        id_or_name: str,
        fieldname: str | dict[str, Any],
        value: Any = None,
    ) -> None:
        """Update one or more fields directly — lightweight, no lifecycle hooks.

        Checks write permission then issues a single SQL UPDATE.
        Use :meth:`save_doc` when you need ``before_save``/``after_save`` hooks
        to run (e.g. validation, audit log)::

            # single field
            await grunt.set_value("Invoice", invoice_id, "status", "Paid")

            # multiple fields at once
            await grunt.set_value("Invoice", invoice_id, {"status": "Paid", "paid_at": now})
        """
        _, _, _ = await self._write_guard(doctype, "write")
        await self.db.set_value(doctype, id_or_name, fieldname, value)
        await self._invalidate_list_cache(doctype)

    async def get_single(self, doctype: str, fieldname: str) -> Any:
        """Fetch a field value from a Single DocType (singleton document).

        Single DocTypes hold global settings and have no id — they are stored
        as key/value rows rather than regular documents::

            currency = await grunt.get_single("SystemSettings", "default_currency")
        """
        return await self.db.get_single_value(doctype, fieldname)

    async def submit(
        self,
        doctype: str,
        doc_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Apply a workflow transition to a document.

        ``action`` must match a transition label defined in the DocType's workflow.
        Raises ``HTTPException(409)`` if the transition is not available for the
        current document state or the user lacks the required role::

            await grunt.submit("LeaveRequest", request_id, "Approve")
        """
        from grunt.core.workflow.engine import workflow_engine  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        return await workflow_engine.apply_transition(
            dt,
            doc_id,
            action,
            self._require_user(),
            self._require_session(),
            self._require_engine(),
        )

    async def duplicate(
        self,
        doctype: str,
        id_or_name: str,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a copy of a document and return it.

        Optionally pass ``overrides`` to change specific fields on the copy::

            draft = await grunt.duplicate("Invoice", original_id, overrides={"status": "Draft"})
        """
        original = await self.get_doc(doctype, id_or_name)
        data = {k: v for k, v in original.items() if k not in ("id", "name", "created_at")}
        if overrides:
            data.update(overrides)
        return await self.new_doc(doctype, data)
