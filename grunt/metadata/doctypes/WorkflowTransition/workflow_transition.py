"""Controller for the ``WorkflowTransition`` DocType."""

from grunt.document.base import Document


class WorkflowTransition(Document):
    """DocType controller for WorkflowTransition."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from_state: str  # From state
    to_state: str  # To state
    action: str  # Action (button text)
    allowed_roles: str | None = None  # Allowed roles (comma-separated)
    condition: str | None = None  # Condition (eval:)
    prompt_fields: str | None = None  # Dialog fields (comma-separated)
    require_comment: bool | None = None  # Comment required
    on_edit: bool | None = None  # Apply on edit
    deny_self_approval: bool | None = None  # Not by the author
    confirm: bool | None = None  # Ask for confirmation

    # end: auto-generated types
