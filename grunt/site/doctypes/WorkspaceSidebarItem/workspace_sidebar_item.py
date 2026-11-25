"""Controller for the ``WorkspaceSidebarItem`` DocType."""

from grunt.document.base import Document


class WorkspaceSidebarItem(Document):
    """DocType controller for WorkspaceSidebarItem."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    type: str | None = None  # Type
    section: str | None = None  # Section
    label: str | None = None  # Name
    icon: str | None = None  # Icon
    link_doctype: str | None = None  # Link DocType
    link_to: str | None = None  # Links to
    is_singleton: bool | None = None  # Singleton (one record)
    show_count: bool | None = None  # Show count
    count_filters: str | None = None  # Count filters (JSON)
    roles: str | None = None  # Roles (comma-separated)
    source_app: str | None = None  # Added by app
    anchor_after: str | None = None  # Place after
    anchor_before: str | None = None  # Place before

    # end: auto-generated types
