"""Controller for the ``WorkspaceSection`` DocType."""

from grunt.document.base import Document


class WorkspaceSection(Document):
    """DocType controller for WorkspaceSection."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    section: str  # Section
    icon: str | None = None  # Icon
    source_app: str | None = None  # Added by app
    anchor_after: str | None = None  # Place after
    anchor_before: str | None = None  # Place before

    # end: auto-generated types
