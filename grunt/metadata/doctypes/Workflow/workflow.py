"""Controller for the ``Workflow`` DocType."""

from typing import Any

from grunt.document.base import Document


class Workflow(Document):
    """DocType controller for Workflow."""

    document_type: str | None
    is_active: bool | None
    workflow_state_field: str | None
    states: list[dict[str, Any]]  # Table: WorkflowState
    transitions: list[dict[str, Any]]  # Table: WorkflowTransition
    positions: dict | None
    is_standard: bool | None
    app: str | None
