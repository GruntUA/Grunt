"""Pydantic schemas for the Meta API (DocType CRUD responses)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class IndexHint(BaseModel):
    field: str
    reason: str


class DocTypeSaveResult(BaseModel):
    success: bool = True
    data: DocTypeSchema
    hints: list[IndexHint] = []
    exported_to: str | None = None


class DocFieldSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fieldname: str
    label: str = ""
    fieldtype: str

    required: bool = False
    unique: bool = False
    index: bool = False
    read_only: bool = False
    hidden: bool = False

    in_list_view: bool = False
    in_filter: bool = False
    in_quick_filter: bool = False
    bold: bool = False

    options: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    collapsible: bool = False
    columns: int = 12

    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None

    depends_on: str | None = None
    mandatory_depends_on: str | None = None

    group_by: str | None = None


class DocPermissionSchema(BaseModel):
    role: str
    read: bool = False
    write: bool = False
    create: bool = False
    delete: bool = False
    submit: bool = False
    report: bool = False
    match: str | None = None


class WorkflowStateSchema(BaseModel):
    name: str
    label: str
    color: str = "gray"
    is_initial: bool = False
    is_final: bool = False


class WorkflowTransitionSchema(BaseModel):
    from_state: str
    to_state: str
    action: str
    allowed_roles: list[str] = []
    condition: str | None = None


class WorkflowDefSchema(BaseModel):
    state_field: str = "status"
    states: list[WorkflowStateSchema] = []
    transitions: list[WorkflowTransitionSchema] = []
    positions: dict[str, dict[str, float]] = {}


class QuickFilterOnChangeSchema(BaseModel):
    mode: Literal["local", "external"] = "local"
    source: str | None = None
    debounce_ms: int = 300


class QuickFilterSchema(BaseModel):
    id: str
    field: str
    operator: str = "eq"
    label: str | None = None
    input_type: str = "text"
    default_value: str | None = None
    options: list[str] | None = None
    on_change: QuickFilterOnChangeSchema = QuickFilterOnChangeSchema()
    enabled_in: list[Literal["list", "tree"]] = ["list", "tree"]


class CalendarSourceSchema(BaseModel):
    doctype: str
    date_field: str
    end_date_field: str | None = None
    label_field: str | None = None
    color: str | None = None
    filters: dict[str, str] = {}
    recurring: bool = False
    event_type: Literal["default", "birthday"] = "default"
    show_age: bool = False


class DocTypeMapViewSchema(BaseModel):
    geo_field: str | None = None
    label_field: str | None = None
    color_field: str | None = None
    color_map: dict[str, str] | None = None
    default_color: str | None = None
    icon_field: str | None = None


class StatusIndicatorSchema(BaseModel):
    value: str
    color: str = "secondary"
    icon: str | None = None
    label: str | None = None


class DocTypeActionSchema(BaseModel):
    action: str = ""
    label: str = ""
    group: str = ""
    variant: str = ""
    condition: str | None = None
    hidden: bool = False


class DocTypeLinkSchema(BaseModel):
    link_doctype: str = ""
    link_fieldname: str = ""
    parent_doctype: str | None = None
    table_fieldname: str | None = None
    group: str = ""
    label: str = ""
    hidden: bool = False


class DocTypeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    module: str

    is_child: bool = False
    is_submittable: bool = False
    is_singleton: bool = False
    track_changes: bool = True
    track_seen: bool = False
    track_views: bool = False
    quick_entry: bool = False
    beta: bool = False
    deprecated: bool = False

    fields: list[DocFieldSchema] = []

    permissions: list[DocPermissionSchema] = []
    workflow: WorkflowDefSchema | None = None

    autoname: str | None = None
    title_field: str = "name"
    search_fields: list[str] = []

    default_view: str | None = None
    image_field: str | None = None

    form_show_sidebar: bool = True
    quick_filters: list[QuickFilterSchema] = []
    kanban_column_field: str | None = None
    calendar_date_field: str | None = None
    calendar_end_date_field: str | None = None
    calendar_title_field: str | None = None
    calendar_sources: list[CalendarSourceSchema] = []
    map_view: DocTypeMapViewSchema | None = None
    gantt_start_field: str | None = None
    gantt_end_field: str | None = None
    gantt_title_field: str | None = None
    gantt_progress_field: str | None = None
    gantt_color_field: str | None = None
    gantt_color_map: dict[str, str] | None = None
    gantt_default_color: str | None = None
    gantt_dependencies_field: str | None = None
    tree_parent_field: str | None = None
    tree_title_field: str | None = None
    tree_as_of_date_field: str | None = None
    tree_sort_by: str | None = None
    tree_sort_order: Literal["asc", "desc"] = "asc"
    status_field: str | None = None
    status_indicators: list[StatusIndicatorSchema] = []
    actions: list[DocTypeActionSchema] = []
    links: list[DocTypeLinkSchema] = []


DocTypeSaveResult.model_rebuild()


class DocTypeListItem(BaseModel):
    name: str
    label: str
    module: str
    is_child: bool
    is_singleton: bool


class DocTypeSyncResult(BaseModel):
    name: str
    table_name: str
    columns_added: list[str]
    message: str
