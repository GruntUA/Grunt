"""Controller for the ``UserViewSettings`` DocType - see grunt.api.v1.view_settings."""

from grunt.document.base import Document


class UserViewSettings(Document):
    """A user's settings of one view of a DocType (owner == the user)."""

    ref_doctype: str | None
    view: str | None
    settings: dict | list | None
