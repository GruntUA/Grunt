"""DocTypePermission controller and metadata model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from grunt.core.document.base import Document


class DocTypePermission(BaseModel):
    """Pydantic model for DocType permissions inside DocType metadata."""

    model_config = ConfigDict(extra="ignore")

    role: str
    read: bool = False
    write: bool = False
    create: bool = False
    delete: bool = False
    submit: bool = False
    cancel: bool = False
    report: bool = False
    # Row-level filter — e.g. "owner == user"
    match: str | None = None
    # Fields hidden for this role (field names)
    hidden_fields: list[str] = []


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
