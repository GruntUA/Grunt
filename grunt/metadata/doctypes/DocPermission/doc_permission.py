"""Controller for the ``DocPermission`` DocType."""

from grunt.document.base import Document


class DocPermission(Document):
    """DocType controller for DocPermission."""

    role: str | None
    read: bool | None
    select: bool | None
    write: bool | None
    create: bool | None
    # "delete" field: read it as self.data["delete"] - self.delete is the delete() method.
    report: bool | None
    match: str | None
    hidden_fields: str | None
