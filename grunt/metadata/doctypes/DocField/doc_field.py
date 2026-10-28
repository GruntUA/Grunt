"""Controller for the ``DocField`` DocType."""

from grunt.document.base import Document


class DocField(Document):
    """DocType controller for DocField."""

    label: str | None
    fieldname: str | None
    fieldtype: str | None
    options: str | None
    required: bool | None
    unique: bool | None
    read_only: bool | None
    in_list_view: bool | None
    in_filter: bool | None
    hidden: bool | None
    description: str | None
    default: str | None
    depends_on: str | None
