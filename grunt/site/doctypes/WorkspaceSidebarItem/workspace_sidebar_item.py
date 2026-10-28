"""Controller for the ``WorkspaceSidebarItem`` DocType."""

from grunt.document.base import Document


class WorkspaceSidebarItem(Document):
    """DocType controller for WorkspaceSidebarItem."""

    type: str | None
    section: str | None
    label: str | None
    icon: str | None
    link_doctype: str | None
    link_to: str | None
    is_singleton: bool | None
    show_count: bool | None
    count_filters: str | None
    roles: str | None
    source_app: str | None
    anchor_after: str | None
    anchor_before: str | None
