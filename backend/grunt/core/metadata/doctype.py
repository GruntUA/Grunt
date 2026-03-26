"""DocType — the central metadata model of the Grunt framework.

A DocType describes a data structure (fields, views, workflow, permissions)
and is the single source of truth for DB tables, REST API and UI forms.
"""

from typing import Any, Literal

from pydantic import BaseModel

from grunt.core.metadata.field import DocField


# ── Workflow sub-models ──────────────────────────────────────────────────


class WorkflowState(BaseModel):
    name: str
    label: str
    color: str = "gray"  # gray, blue, green, yellow, red
    is_initial: bool = False
    is_final: bool = False


class WorkflowTransition(BaseModel):
    from_state: str
    to_state: str
    action: str  # button label
    allowed_roles: list[str] = []
    condition: str | None = None  # Python expression


class DocTypeWorkflow(BaseModel):
    states: list[WorkflowState]
    transitions: list[WorkflowTransition]
    state_field: str = "status"  # field that stores current state


# ── Permission sub-model ─────────────────────────────────────────────────


class DocTypePermission(BaseModel):
    role: str
    read: bool = False
    write: bool = False
    create: bool = False
    delete: bool = False
    submit: bool = False
    report: bool = False
    # Row-level filter — e.g. "owner == user"
    match: str | None = None


# ── View configuration sub-models ────────────────────────────────────────


class DocTypeListView(BaseModel):
    fields: list[str] = []  # field names to display
    sort_by: str = "modified"
    sort_order: Literal["asc", "desc"] = "desc"
    default_filters: dict[str, str] = {}


class DocTypeFormView(BaseModel):
    layout: Literal["standard", "compact", "wide"] = "standard"
    print_format: str | None = None


class DocTypeKanbanView(BaseModel):
    column_field: str  # Select field for columns
    title_field: str = "name"
    color_field: str | None = None


class CalendarSource(BaseModel):
    """Additional document source for the calendar view."""

    doctype: str
    date_field: str
    end_date_field: str | None = None
    label_field: str | None = None
    color: str | None = None
    filters: dict[str, Any] | None = None


class DocTypeCalendarView(BaseModel):
    """Configuration for the calendar view (Phase 2)."""

    field: str  # Principal date field
    end_field: str | None = None
    title_field: str = "name"
    sources: list[CalendarSource] = []


# ── DocType — main model ─────────────────────────────────────────────────


class DocType(BaseModel):
    """Top-level metadata definition for a document type."""

    name: str  # PascalCase, globally unique
    label: str  # "Договір постачання"
    module: str  # "crm"

    # Flags
    is_child: bool = False  # True → used inside a TABLE field
    is_submittable: bool = False  # adds Submit button
    is_singleton: bool = False  # only one document per DocType
    is_virtual: bool = False  # True → no DB table, data from controller
    track_changes: bool = True  # audit log

    # Fields
    fields: list[DocField] = []

    # View configuration
    list_view: DocTypeListView = DocTypeListView()
    form_view: DocTypeFormView = DocTypeFormView()
    kanban_view: DocTypeKanbanView | None = None
    calendar_view: DocTypeCalendarView | None = None

    # Business logic
    workflow: DocTypeWorkflow | None = None
    permissions: list[DocTypePermission] = []

    # Naming
    autoname: str | None = None  # "CONTR-.YYYY.-.####" or "field:title"
    title_field: str = "name"  # field used as document title

    # Search
    search_fields: list[str] = []

    model_config = {"use_enum_values": True}
