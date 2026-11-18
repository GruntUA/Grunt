"""Controller for the ``SavedFilter`` DocType - see grunt.api.v1.saved_filters."""

from grunt.document.base import Document


class SavedFilter(Document):
    """Named list filters of one DocType; shared with nobody, roles or everyone."""

    title: str | None
    ref_doctype: str | None
    filters: list | None
    shared_with: str | None
    roles: list | None
