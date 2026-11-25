"""Controller for the ``SavedFilter`` DocType - see grunt.api.v1.saved_filters."""

from typing import Any

from grunt.document.base import Document


class SavedFilter(Document):
    """Named list filters of one DocType; shared with nobody, roles or everyone."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    ref_doctype: str  # Document type
    filters: Any | None = None  # Filters
    shared_with: str | None = None  # Shared with
    roles: Any | None = None  # Roles

    # end: auto-generated types
