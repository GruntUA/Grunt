"""Controller for the ``DocVersion`` DocType."""

from grunt.document.base import Document


class DocVersion(Document):
    """DocType controller for DocVersion."""

    ref_doctype: str | None
    doc_id: str | None
    version: int | None
    # "user" field: read it as self.data["user"] - self.user is the session user.
    changes: dict | None
