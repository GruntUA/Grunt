"""Controller for the ``UserViewSettings`` DocType - see grunt.api.v1.view_settings."""

from typing import Any

from grunt.document.base import Document


class UserViewSettings(Document):
    """A user's settings of one view of a DocType (owner == the user)."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    view: str  # View
    settings: Any | None = None  # Settings

    # end: auto-generated types
