"""Virtual DocType delegation for the document pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import HTTPException, status

from grunt.document.registry import document_registry

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.document.base import DocumentList


def is_virtual_routed(dt: Any, doctype_name: str) -> bool:
    """True якщо CRUD треба делегувати VirtualDocType-контролеру.

    Перевіряє dt.is_virtual АБО наявність зареєстрованого VirtualDocType-контролера.
    Це дозволяє DocType мати is_virtual=False (нормальний merge при install),
    але продовжувати маршрутизувати CRUD через DocTypeController.
    """
    from grunt.document.base import Document
    from grunt.metadata.virtual import VirtualDocType

    if dt.is_virtual:
        return True
    ctrl_cls = document_registry.get(doctype_name)
    return ctrl_cls is not Document and issubclass(ctrl_cls, VirtualDocType)


def _get_virtual_controller(doctype_name: str, user: User):
    """Get the VirtualDocType controller instance for a virtual DocType, or
    ``None`` when it has none (e.g. a virtual child table whose rows exist only
    inside the parent document) — such a DocType simply has no documents."""
    from grunt.metadata.virtual import VirtualDocType

    controller_cls = document_registry.get(doctype_name)
    if issubclass(controller_cls, VirtualDocType):
        return cast("type[VirtualDocType]", controller_cls)(doctype_name, user)
    return None


def _no_controller(doctype_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Віртуальний DocType «{doctype_name}» не має окремих документів",
    )


async def virtual_list(
    doctype_name: str,
    user: User,
    page: int,
    per_page: int,
    sort_by: str,
    sort_order: str,
    filters: Any,
    search: str | None,
) -> DocumentList:
    from grunt.document.base import DocumentList

    ctrl = _get_virtual_controller(doctype_name, user)
    if ctrl is None:
        return DocumentList(data=[], meta={"total": 0, "page": page, "per_page": per_page})
    result = await ctrl.get_list(
        filters=filters,
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
    )
    if isinstance(result, DocumentList):
        return result
    return DocumentList(data=result.get("data", []), meta=result.get("meta", {}))


async def virtual_get(doctype_name: str, user: User, doc_id: str):
    ctrl = _get_virtual_controller(doctype_name, user)
    if ctrl is None:
        raise _no_controller(doctype_name)
    return await ctrl.get(doc_id)


async def virtual_create(doctype_name: str, user: User, data: dict[str, Any]):
    ctrl = _get_virtual_controller(doctype_name, user)
    if ctrl is None:
        raise _no_controller(doctype_name)
    return await ctrl.create(data)


async def virtual_update(doctype_name: str, user: User, doc_id: str, data: dict[str, Any]):
    ctrl = _get_virtual_controller(doctype_name, user)
    if ctrl is None:
        raise _no_controller(doctype_name)
    return await ctrl.update(doc_id, data)


async def virtual_delete(doctype_name: str, user: User, doc_id: str):
    ctrl = _get_virtual_controller(doctype_name, user)
    if ctrl is None:
        raise _no_controller(doctype_name)
    return await ctrl.delete(doc_id)
