"""Controller for the ``WorkspaceSection`` DocType."""

from grunt.document.base import Document


class WorkspaceSection(Document):
    """DocType controller for WorkspaceSection."""

    section: str | None
    icon: str | None
    source_app: str | None
    anchor_after: str | None
    anchor_before: str | None
