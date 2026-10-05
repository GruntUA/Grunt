"""CRUD operations for Documents."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Body, Depends, Query, Request, status

import grunt
from grunt import _
from grunt.api.router import GruntRouter
from grunt.api.v1.docs.utils import parse_query_filters
from grunt.api.v1.schemas.response import ok
from grunt.auth.dependencies import current_user
from grunt.auth.doctypes.User.user import User
from grunt.document.bulk_ops import BulkDeleteTask
from grunt.permissions.doc_perms import PERMS_KEY, with_permissions
from grunt.website.generator import WEB_URL_KEY, with_web_url

router = GruntRouter()


async def _decorate(doctype: str, doc: Any) -> Any:
    """The form's computed extras: ``__perms`` and, for a web page, ``__web_url``."""
    return await with_web_url(doctype, await with_permissions(doctype, doc))


@router.get("/{doctype}")
async def list_documents(
    doctype: str,
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=10000),
    sort_by: str = "modified_at",
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    search: str | None = None,
    fields: str | None = None,
    cursor: str | None = Query(None, description="Opaque cursor for keyset pagination"),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """List documents for a DocType."""
    merged_filters = parse_query_filters(request)
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

    result = await grunt.get_list(
        doctype,
        filters=merged_filters if merged_filters else None,
        fields=field_list,
        limit=per_page,
        page=page,
        order_by=sort_by,
        order=sort_order,
        search=search,
        cursor=cursor,
    )
    return ok(**result.to_dict())


@router.post("/{doctype}", status_code=status.HTTP_201_CREATED)
async def create_document(
    doctype: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Create a new document."""
    body.pop(PERMS_KEY, None)  # computed, never stored
    body.pop(WEB_URL_KEY, None)
    doc = await grunt.new_doc(doctype, body)
    return ok(await _decorate(doctype, doc))


@router.get("/{doctype}/{doc_id}")
async def get_document(
    doctype: str,
    doc_id: str,
    expand: str | None = Query(None, description="Comma-separated relation fields to expand"),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Get document data."""
    expand_fields = [f.strip() for f in expand.split(",") if f.strip()] if expand else None
    doc = await grunt.get_doc(doctype, doc_id, expand=expand_fields)
    return ok(await _decorate(doctype, doc))


@router.put("/{doctype}/{doc_id}")
async def update_document(
    doctype: str,
    doc_id: str,
    body: dict[str, Any] = Body(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Update an existing document."""
    body.pop(PERMS_KEY, None)  # computed, never stored
    body.pop(WEB_URL_KEY, None)
    doc = await grunt.save_doc(doctype, doc_id, body)
    return ok(await _decorate(doctype, doc))


@router.delete("/{doctype}/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doctype: str,
    doc_id: str,
    replace_with: str | None = None,
    user: User = Depends(current_user),
) -> None:
    """Delete a document.

    ``replace_with`` - repoint every reference to this document at the given
    surviving document of the same DocType before deleting.
    """
    await grunt.delete_doc(doctype, doc_id, replace_with)


@grunt.whitelist()
async def rename(doctype: str, doc_id: str, new_name: str) -> dict[str, Any]:
    """Rename a document (change its id). RPC: grunt.api.v1.docs.crud.rename"""
    return await grunt.rename_doc(doctype, doc_id, new_name)


@grunt.whitelist()
async def bulk_delete(
    doctype: str,
    ids: list[str] | None = None,
    delete_all: bool = False,
    filters: dict[str, Any] | None = None,
    search: str | None = None,
    fast: bool = False,
    replace_with: str | None = None,
) -> dict[str, Any]:
    """Delete multiple documents by IDs, or all documents matching filters.

    RPC: grunt.api.v1.docs.crud.bulk_delete

    Deletion runs as a background task; progress is pushed via WebSocket
    (event ``bulk_delete_progress`` / ``bulk_delete_done``) to the requesting user.

    Either pass ``ids`` (delete by explicit IDs) or ``delete_all=true`` with
    optional ``filters``/``search`` (delete all matching, in rolling batches
    so datasets of any size are supported).
    """
    from grunt.site.manager import current_site

    user = grunt.get_user()
    user_email = user.email
    engine = grunt.get_engine()
    task = BulkDeleteTask()
    active_site = current_site.get()

    if delete_all:
        if fast:
            # Fast path: direct SQL DELETE, System Manager only
            async def _run_fast() -> None:
                if active_site:
                    current_site.set(active_site)
                await task.run_fast_delete_all(
                    doctype,
                    filters=filters,
                    user=user,
                    user_email=user_email,
                    engine=engine,
                )

            asyncio.create_task(_run_fast())
            return {"started": True, "total": None, "fast": True}

        async def _run_all() -> None:
            if active_site:
                current_site.set(active_site)
            await task.run_delete_all(
                doctype,
                filters=filters,
                search=search,
                user=user,
                user_email=user_email,
                engine=engine,
            )

        asyncio.create_task(_run_all())
        return {"started": True, "total": None}

    # Explicit IDs path
    if not ids:
        grunt.throw(_("ids or delete_all is required"))

    total = len(ids)

    async def _run() -> None:
        if active_site:
            current_site.set(active_site)
        await task.run(
            doctype,
            ids,
            user=user,
            user_email=user_email,
            engine=engine,
            replace_with=replace_with,
        )

    asyncio.create_task(_run())
    return {"started": True, "total": total}


@grunt.whitelist()
async def bulk_update(
    doctype: str, ids: list[str], field: str, value: Any = None
) -> dict[str, Any]:
    """Update a single field on multiple documents.

    RPC: grunt.api.v1.docs.crud.bulk_update
    """
    if not ids:
        grunt.throw(_("ids is required"))
    if not field:
        grunt.throw(_("field is required"))

    updated = 0
    errors: list[str] = []
    for doc_id in ids:
        try:
            await grunt.save_doc(doctype, doc_id, {field: value})
            updated += 1
        except Exception as e:
            errors.append(f"{doc_id}: {e}")

    return {"updated": updated, "errors": errors}
