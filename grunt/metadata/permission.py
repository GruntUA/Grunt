"""DocType permission metadata model.

Lives in the metadata layer (no dependency on ``grunt.document.base``) so that
``grunt.metadata.doctype`` can reference it during bootstrap without importing a
Document controller — which would invert the metadata→document layering and
create an import cycle.

Permissions are stored inline on the owning DocType (``doctype.permissions``,
a list of these) and edited in the Studio DocType builder's "Дозволи" tab via
the ``DocPermission`` child schema. There is no standalone permission store.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DocPermission(BaseModel):
    """Pydantic model for a single permission row inside DocType metadata."""

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
