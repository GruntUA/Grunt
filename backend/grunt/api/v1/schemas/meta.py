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

    permissions: list[dict[str, Any]] = []
    workflow: dict[str, Any] | None = None

    autoname: str | None = None
    title_field: str = "name"
    search_fields: list[str] = []


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
