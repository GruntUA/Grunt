"""Controller for the ``DocLink`` DocType."""

from grunt.document.base import Document


class DocLink(Document):
    """DocType controller for DocLink."""

    source_doctype: str | None
    source_id: str | None
    target_doctype: str | None
    target_id: str | None
    link_fieldname: str | None
