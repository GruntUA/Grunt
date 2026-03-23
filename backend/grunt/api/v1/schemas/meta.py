"""Pydantic schemas for the Meta API (DocType CRUD responses)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class DocFieldSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fieldname: str
    label: str
    fieldtype: str

    required: bool = False
    unique: bool = False
    read_only: bool = False
    hidden: bool = False

    in_list_view: bool = False
    in_filter: bool = False
    bold: bool = False

    options: str | None = None
    default: Any = None
    description: str | None = None
    placeholder: str | None = None

    collapsible: bool = False
    columns: Literal[1, 2, 3, 4] = 1

    min_value: float | None = None
    max_value: float | None = None
    max_length: int | None = None
    regex: str | None = None

    depends_on: str | None = None
    mandatory_depends_on: str | None = None


class DocTypePermissionSchema(BaseModel):
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


class DocTypeListViewSchema(BaseModel):
    fields: list[str] = []
    sort_by: str = "modified"
    sort_order: Literal["asc", "desc"] = "desc"
    default_filters: dict[str, str] = {}


class DocTypeFormViewSchema(BaseModel):
    layout: Literal["standard", "compact", "wide"] = "standard"
    print_format: str | None = None


class DocTypeKanbanViewSchema(BaseModel):
    column_field: str
    title_field: str = "name"
    color_field: str | None = None


class DocTypeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    module: str

    is_child: bool = False
    is_submittable: bool = False
    is_singleton: bool = False
    track_changes: bool = True

    fields: list[DocFieldSchema] = []

    permissions: list[DocTypePermissionSchema] = []
    workflow: WorkflowDefSchema | None = None

    autoname: str | None = None
    title_field: str = "name"
    search_fields: list[str] = []

    list_view: DocTypeListViewSchema = DocTypeListViewSchema()
    form_view: DocTypeFormViewSchema = DocTypeFormViewSchema()
    kanban_view: DocTypeKanbanViewSchema | None = None


class DocTypeListItem(BaseModel):
    name: str
    label: str
    module: str
    is_child: bool


class DocTypeSyncResult(BaseModel):
    name: str
    table_name: str
    columns_added: list[str]
    message: str
