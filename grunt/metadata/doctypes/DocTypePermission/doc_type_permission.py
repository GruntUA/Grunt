"""DocTypePermission controller.

The ``DocTypePermission`` Pydantic model now lives in
:mod:`grunt.metadata.permission` (re-exported below for backward compatibility)
so the metadata layer can reference it without importing this controller module.
"""

from __future__ import annotations

from grunt.document.base import Document
from grunt.metadata.permission import DocTypePermission

__all__ = ["DocTypePermission", "DocTypePermissionController"]


class DocTypePermissionController(Document):
    """Controller for DocTypePermission documents."""

    doctype_name: str
    role: str
    read: bool
    write: bool
    create: bool
    delete: bool  # type: ignore[assignment]
    submit: bool
    cancel: bool
    report: bool
    match: str | None
    hidden_fields: str | None
