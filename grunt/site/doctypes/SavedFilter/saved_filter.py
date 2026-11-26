"""Controller for the ``SavedFilter`` DocType - see grunt.api.v1.saved_filters."""

from typing import Any

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _


class SavedFilter(Document):
    """Named list filters of one DocType; shared with nobody, roles or everyone."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    ref_doctype: str  # Document type
    filters: Any | None = None  # Filters
    shared_with: str | None = None  # Shared with
    roles: Any | None = None  # Roles
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App

    # end: auto-generated types

    async def validate(self) -> None:
        # An app's filter belongs to no user: unshared, nobody would see it.
        if self.is_standard and (self.shared_with or "Nobody") == "Nobody":
            throw(
                _("A standard filter must be shared with roles or with everyone"),
                "VALIDATION_ERROR",
            )
