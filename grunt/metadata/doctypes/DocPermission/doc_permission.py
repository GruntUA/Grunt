"""Controller for the ``DocPermission`` DocType."""

from grunt.document.base import Document


class DocPermission(Document):
    """DocType controller for DocPermission."""

    role: str | None
    actions: list[str] | None
    match: str | None
    hidden_fields: str | None
    readonly_fields: str | None
