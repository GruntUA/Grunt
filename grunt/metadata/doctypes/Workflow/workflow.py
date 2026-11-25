"""Controller for the ``Workflow`` DocType."""

from typing import Any

from grunt.document.base import Document
from grunt.metadata.doctypes.WorkflowState.workflow_state import WorkflowState
from grunt.metadata.doctypes.WorkflowTransition.workflow_transition import WorkflowTransition


class Workflow(Document):
    """DocType controller for Workflow."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    document_type: str  # DocType
    is_active: bool | None = None  # Active
    workflow_state_field: str | None = None  # State field
    positions: Any | None = None  # Node positions
    is_standard: bool | None = None  # Standard
    app: str | None = None  # App
    states: list[WorkflowState] = []  # States
    transitions: list[WorkflowTransition] = []  # Transitions

    # end: auto-generated types
