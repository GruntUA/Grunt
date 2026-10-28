"""Controller for the ``DocTypeLink`` DocType."""

from grunt.document.base import Document


class DocTypeLink(Document):
    """DocType controller for DocTypeLink."""

    link_doctype: str | None
    link_fieldname: str | None
    group: str | None
    label: str | None
    hidden: bool | None
    parent_doctype: str | None
    table_fieldname: str | None
