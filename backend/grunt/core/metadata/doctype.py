"""DocType — the central metadata model of the Grunt framework.

A DocType describes a data structure (fields, views, workflow, permissions)
and is the single source of truth for DB tables, REST API and UI forms.
"""

from typing import Any, Literal

from pydantic import BaseModel

from grunt.core.doctypes.doc_type_permission.doc_type_permission import DocTypePermission
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


class WorkflowStep(BaseModel):
    id: str
    name: str
    title: str = ""
    step_type: str = (
        "state"  # state | form | approval | notification | script | condition | create_doc | stop
    )
    variable: str | None = None  # variable binding (e.g. req.vars.input_docs)
    sequence: int = 0
    is_active: bool = True
    next_steps: list[str] = []  # names of next steps
    config: dict[str, Any] = {}


class DocTypeWorkflow(BaseModel):
    states: list[WorkflowState]
    transitions: list[WorkflowTransition]
    state_field: str = "status"  # field that stores current state
    steps: list[WorkflowStep] = []
    positions: dict[str, dict[str, float]] = {}  # graph editor node positions {state_name: {x, y}}


# ── Permission sub-model ─────────────────────────────────────────────────


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


class DocTypeTreeView(BaseModel):
    """Configuration for the tree view — hierarchical documents via a self-referential Link."""

    parent_field: str  # fieldname of the Link field pointing to the same DocType
    title_field: str = "name"  # field displayed as node label


class DocTypeMapView(BaseModel):
    """Configuration for the map view — requires a Geolocation field."""

    geo_field: str | None = None  # override auto-detected Geolocation field
    label_field: str | None = None  # field shown in marker popup (defaults to title_field)
    color_field: str | None = None  # field whose value drives marker color
    color_map: dict[str, str] | None = None  # { value: '#hex' } mapping for color_field
    default_color: str | None = None  # fallback marker color


# ── Status indicators ───────────────────────────────────────────────────


class StatusIndicator(BaseModel):
    """Maps a field value to a color and optional icon for status display."""

    value: str  # field value to match
    color: str = "secondary"  # default|secondary|success|info|warn|danger|contrast
    icon: str | None = None  # Lucide icon name, e.g. "circle-check"
    label: str | None = None  # override display label (defaults to value)


class DocTypeStatusConfig(BaseModel):
    """Configures how document status is displayed in list/form views."""

    field: str  # fieldname that represents status
    indicators: list[StatusIndicator] = []


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
    is_tree: bool = False  # True → hierarchical; requires tree_view.parent_field
    is_log: bool = False  # True → operational log, excluded from global search index
    # to name the self-referential Link
    track_changes: bool = True  # audit log
    quick_entry: bool = False  # True → "Create" opens a dialog instead of full form

    # Fields
    fields: list[DocField] = []

    # View configuration
    default_view: str | None = None  # "list" | "kanban" | "calendar" | "tree" | "map"
    list_view: DocTypeListView = DocTypeListView()
    form_view: DocTypeFormView = DocTypeFormView()
    kanban_view: DocTypeKanbanView | None = None
    calendar_view: DocTypeCalendarView | None = None
    tree_view: DocTypeTreeView | None = None
    map_view: DocTypeMapView | None = None

    # Status display
    status_config: DocTypeStatusConfig | None = None

    # Business logic
    workflow: DocTypeWorkflow | None = None
    permissions: list[DocTypePermission] = []

    # Naming / display
    autoname: str | None = None  # "CONTR-.YYYY.-.####" or "field:title"
    title_field: str = "name"  # field used as document title
    image_field: str | None = None  # field (Image/Attach) used as document avatar

    # Search
    search_fields: list[str] = []

    # Override physical table name — used to pin core/system DocTypes to their
    # legacy ORM table names (e.g. "grunt_server_script" instead of "grunt_core_server_script").
    table_name: str | None = None

    model_config = {"use_enum_values": True}
