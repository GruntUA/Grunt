"""DocType — the central metadata model of the Grunt framework.

A DocType describes a data structure (fields, views, workflow, permissions)
and is the single source of truth for DB tables, REST API and UI forms.
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from grunt.metadata.field import DocField
from grunt.metadata.permission import DocTypePermission

# ── Workflow sub-models ──────────────────────────────────────────────────


class WorkflowState(BaseModel):
    """Runtime shape of a ``WorkflowState`` child row, as read off a ``Workflow`` document."""

    state: str  # value stored in the target document's state field
    label: str = ""
    color: str = "gray"  # gray, blue, green, yellow, orange, red
    is_initial: bool = False
    is_final: bool = False


class WorkflowTransition(BaseModel):
    """Runtime shape of a ``WorkflowTransition`` child row, as read off a ``Workflow`` document."""

    from_state: str
    to_state: str
    action: str  # button label
    allowed_roles: list[str] = []
    condition: str | None = None  # Python expression

    @model_validator(mode="before")
    @classmethod
    def _split_allowed_roles(cls, data: Any) -> Any:
        """``allowed_roles`` is stored as a comma-separated ``LongText`` field."""
        if isinstance(data, dict) and isinstance(data.get("allowed_roles"), str):
            roles = [r.strip() for r in data["allowed_roles"].split(",") if r.strip()]
            data = {**data, "allowed_roles": roles}
        return data


# ── Permission sub-model ─────────────────────────────────────────────────


# ── View configuration sub-models ────────────────────────────────────────

_FAST_FILTER_OPERATORS: frozenset[str] = frozenset(
    {
        "eq",
        "ne",
        "neq",
        "ilike",
        "like",
        "gt",
        "lt",
        "gte",
        "lte",
        "in",
        "isnull",
        "lte_or_null",
    }
)


class FastFilterOnChange(BaseModel):
    mode: Literal["local", "external"] = "local"
    source: str | None = None  # required when mode="external"; identifies context source
    debounce_ms: int = 300


class FastFilter(BaseModel):
    """A metadata-driven fast filter displayed in the list/tree toolbar."""

    id: str  # unique within the DocType; used as the backend query key prefix
    field: str  # fieldname on the DocType
    operator: str = "eq"  # must be one of _FAST_FILTER_OPERATORS
    label: str | None = None  # display label; falls back to field label when omitted
    input_type: str = "text"  # text | date | select | check | number | link
    default_value: str | None = None
    options: list[str] | None = None  # explicit select options; overrides field.options when set
    on_change: FastFilterOnChange = FastFilterOnChange()
    enabled_in: list[Literal["list", "tree"]] = ["list", "tree"]


class DocTypeListView(BaseModel):
    fields: list[str] = []  # field names to display
    sort_by: str = "modified"
    sort_order: Literal["asc", "desc"] = "desc"
    default_filters: dict[str, str] = {}
    fast_filters: list[FastFilter] = []


class DocTypeFormView(BaseModel):
    layout: Literal["standard", "compact", "wide"] = "standard"
    print_format: str | None = None
    show_sidebar: bool = True  # False → hide the document detail sidebar on the form


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
    recurring: bool = False
    event_type: Literal["default", "birthday"] = "default"
    show_age: bool = False
    remind_before_days: int | None = None


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
    as_of_date_field: str | None = (
        None  # Date field for "as-of" filtering; enables the date picker in tree toolbar
    )
    sort_by: str | None = None  # optional default sort field for tree nodes
    sort_order: Literal["asc", "desc"] = "asc"  # optional default sort direction


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
    app: str | None = None  # installed app name (e.g. "hrm"); UI convenience, derived from module

    # Flags
    is_child: bool = False  # True → used inside a TABLE field
    is_submittable: bool = False  # adds Submit button
    is_singleton: bool = False  # only one document per DocType
    is_virtual: bool = False  # True → no DB table, data from controller
    is_tree: bool = False  # True → hierarchical; requires tree_view.parent_field
    is_log: bool = False  # True → operational log, excluded from global search index
    log_retention_days: int | None = None  # is_log only; None → DEFAULT_LOG_RETENTION_DAYS
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

    @model_validator(mode="after")
    def _validate_fast_filters(self) -> DocType:
        """Validate each fast_filter entry against declared fields and allowed operators."""
        if not self.list_view.fast_filters:
            return self
        field_names = {f.fieldname for f in self.fields}
        seen_ids: set[str] = set()
        for ff in self.list_view.fast_filters:
            if ff.id in seen_ids:
                raise ValueError(f"fast_filter id '{ff.id}' is duplicated. Each id must be unique.")
            seen_ids.add(ff.id)
            if ff.operator not in _FAST_FILTER_OPERATORS:
                raise ValueError(
                    f"fast_filter '{ff.id}': invalid operator '{ff.operator}'. "
                    f"Allowed: {sorted(_FAST_FILTER_OPERATORS)}"
                )
            if ff.field not in field_names:
                raise ValueError(
                    f"fast_filter '{ff.id}': field '{ff.field}' not found in DocType fields."
                )
            if ff.on_change.mode == "external" and not ff.on_change.source:
                raise ValueError(
                    f"fast_filter '{ff.id}': on_change.mode='external' requires "
                    "on_change.source to be set."
                )
        return self
