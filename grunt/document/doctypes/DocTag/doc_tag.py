"""Controller for the ``DocTag`` DocType."""

from grunt.document.base import Document


class DocTag(Document):
    """DocType controller for DocTag."""

    reference_doctype: str | None
    reference_id: str | None
    tag: str | None
