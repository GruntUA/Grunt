"""Controller for the ``WorkflowState`` DocType."""

from grunt.document.base import Document


class WorkflowState(Document):
    """DocType controller for WorkflowState."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    state: str  # Value
    label: str | None = None  # Name
    color: str | None = None  # Color
    is_initial: bool | None = None  # Initial
    is_final: bool | None = None  # Final
    edit_roles: str | None = None  # Edit roles (comma-separated)
    update_field: str | None = None  # Set field
    update_value: str | None = None  # Field value
    message: str | None = None  # Message

    # end: auto-generated types
