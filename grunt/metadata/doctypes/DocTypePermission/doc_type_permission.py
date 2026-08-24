"""DocTypePermission controller.

The ``DocTypePermission`` Pydantic model lives in
:mod:`grunt.metadata.permission` and is re-exported below — not for backward
compatibility, but to avoid an import cycle: ``grunt.metadata.doctype`` needs
this model and must not depend on ``grunt.document.base`` (this controller's
base class), so the model was split out of this module rather than this
module importing it downward.
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
