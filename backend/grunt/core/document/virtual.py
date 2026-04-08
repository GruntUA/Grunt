"""Virtual DocType delegation for DocumentService."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.core.document.registry import document_registry

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser


def _get_virtual_controller(doctype_name: str, user: GruntUser):
    """Get the VirtualDocType controller instance for a virtual DocType."""
    from grunt.core.metadata.virtual import VirtualDocType  # noqa: PLC0415

    controller_cls = document_registry.get(doctype_name)
    # Check if it's a VirtualDocType subclass
    if issubclass(controller_cls, VirtualDocType):
        return controller_cls(doctype_name, user)
    # Fallback — create a base VirtualDocType (will raise NotImplementedError)
    return VirtualDocType(doctype_name, user)


async def _virtual_list(doctype_name: str, user: GruntUser, page: int, per_page: int, sort_by: str, sort_order: str, filters: Any, search: str):
    ctrl = _get_virtual_controller(doctype_name, user)
    return await ctrl.get_list(
        filters=filters, page=page, per_page=per_page,
        sort_by=sort_by, sort_order=sort_order, search=search,
    )


async def _virtual_get(doctype_name: str, user: GruntUser, doc_id: str):
    ctrl = _get_virtual_controller(doctype_name, user)
    return await ctrl.get(doc_id)


async def _virtual_create(doctype_name: str, user: GruntUser, data: dict[str, Any]):
    ctrl = _get_virtual_controller(doctype_name, user)
    return await ctrl.create(data)


async def _virtual_update(doctype_name: str, user: GruntUser, doc_id: str, data: dict[str, Any]):
    ctrl = _get_virtual_controller(doctype_name, user)
    return await ctrl.update(doc_id, data)


async def _virtual_delete(doctype_name: str, user: GruntUser, doc_id: str):
    ctrl = _get_virtual_controller(doctype_name, user)
    return await ctrl.delete(doc_id)
