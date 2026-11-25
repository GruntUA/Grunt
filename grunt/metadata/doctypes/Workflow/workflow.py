"""Controller for the ``Workflow`` DocType."""

from typing import Any

from grunt.document.base import Document


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
    states: list[dict] = []  # Table: WorkflowState
    transitions: list[dict] = []  # Table: WorkflowTransition

    # end: auto-generated types
