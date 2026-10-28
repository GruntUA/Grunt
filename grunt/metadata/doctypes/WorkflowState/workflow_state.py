"""Controller for the ``WorkflowState`` DocType."""

from grunt.document.base import Document


class WorkflowState(Document):
    """DocType controller for WorkflowState."""

    state: str | None
    label: str | None
    color: str | None
    is_initial: bool | None
    is_final: bool | None
    edit_roles: str | None
    update_field: str | None
    update_value: str | None
