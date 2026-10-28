"""Controller for the ``WorkflowTransition`` DocType."""

from grunt.document.base import Document


class WorkflowTransition(Document):
    """DocType controller for WorkflowTransition."""

    from_state: str | None
    to_state: str | None
    action: str | None
    allowed_roles: str | None
    condition: str | None
    prompt_fields: str | None
    require_comment: bool | None
    on_edit: bool | None
    notify: str | None
    notify_email: bool | None
