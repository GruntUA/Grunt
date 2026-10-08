"""Core MCP tools - generic, metadata-driven access to every DocType.

Each tool is a thin wrapper over the grunt SDK, which applies the caller's
permissions (DocType RBAC, row-level rules, permission-hidden fields).
"""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _
from grunt.mcp.registry import mcp_tool
from grunt.metadata.registry import doctype_registry
from grunt.permissions.guards import read_guard
from grunt.permissions.rbac import permission_checker

# Field types that only shape the form layout and carry no data.
_LAYOUT_FIELDTYPES = frozenset({"Tab", "Section", "Column", "Button", "HTML"})

_MAX_LIMIT = 100

_FILTERS_HELP = (
    "Filters are an object of conditions ANDed together. A key is a fieldname with an "
    "optional '__<op>' suffix: eq (default), ne, gt, gte, lt, lte, like, ilike, nlike, "
    "in, nin, isnull, is ('set'/'not set'), year. "
    'Example: {"status": "Open", "amount__gte": 1000, "owner__in": ["a@x.com"]}.'
)

_DOCTYPE_ARG = {
    "type": "string",
    "description": "DocType name exactly as returned by list_doctypes, e.g. 'User'.",
}


def _field_info(field: Any, hidden: frozenset[str]) -> dict[str, Any] | None:
    if field.fieldtype in _LAYOUT_FIELDTYPES or field.fieldname in hidden:
        return None
    info: dict[str, Any] = {
        "fieldname": field.fieldname,
        "label": _(field.label) if field.label else field.fieldname,
        "fieldtype": field.fieldtype,
    }
    if field.options:
        if field.fieldtype == "Select":
            info["options"] = [o for o in field.options.split("\n") if o]
        else:
            # Link / Table / MultiLink: the target DocType.
            info["options"] = field.options
    for flag in ("required", "read_only", "unique"):
        if getattr(field, flag):
            info[flag] = True
    if field.default not in (None, ""):
        info["default"] = field.default
    if field.description:
        info["description"] = _(field.description)
    return info


def _fields(meta: Any, hidden: frozenset[str]) -> list[dict[str, Any]]:
    return [info for f in meta.doc.fields if (info := _field_info(f, hidden)) is not None]


@mcp_tool(
    "list_doctypes",
    title="List DocTypes",
    description=(
        "List the DocTypes (record types / tables) the current user can read. "
        "Start here to discover what data exists, then call describe_doctype."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "module": {"type": "string", "description": "Only DocTypes of this module."},
            "search": {
                "type": "string",
                "description": "Case-insensitive substring of the name or label.",
            },
        },
    },
    read_only=True,
)
async def list_doctypes(module: str | None = None, search: str | None = None) -> list[dict]:
    user = grunt.get_user()
    needle = (search or "").casefold()
    result = []
    for dt in await doctype_registry.list_all():
        if not dt.name or dt.is_child:
            continue
        if module and dt.module != module:
            continue
        label = _(dt.label) if dt.label else dt.name
        if needle and needle not in dt.name.casefold() and needle not in label.casefold():
            continue
        try:
            if not await permission_checker.check(user, dt, "read"):
                continue
        except Exception:
            continue
        entry: dict[str, Any] = {"name": dt.name, "label": label, "module": dt.module}
        if dt.description:
            entry["description"] = _(dt.description)
        if dt.is_singleton:
            entry["is_singleton"] = True
        result.append(entry)
    return result


@mcp_tool(
    "describe_doctype",
    title="Describe DocType",
    description=(
        "Return the fields of a DocType: fieldname, label, fieldtype, Select options, "
        "Link/Table target DocType, required flags. Child tables (fieldtype 'Table') "
        "include their own fields. Call before filtering, creating or updating records."
    ),
    input_schema={
        "type": "object",
        "properties": {"doctype": _DOCTYPE_ARG},
        "required": ["doctype"],
    },
    read_only=True,
)
async def describe_doctype(doctype: str) -> dict[str, Any]:
    meta, user, hidden = await read_guard(doctype)
    dt = meta.doc
    fields = _fields(meta, hidden)
    for info in fields:
        if info["fieldtype"] == "Table" and info.get("options"):
            child = await grunt.get_meta(info["options"])
            if child is not None:
                child_hidden = permission_checker.hidden_fields(user, child)
                info["child_fields"] = _fields(child, child_hidden)
    result: dict[str, Any] = {
        "name": dt.name,
        "label": _(dt.label) if dt.label else dt.name,
        "module": dt.module,
        "title_field": dt.title_field,
        "fields": fields,
    }
    if dt.description:
        result["description"] = _(dt.description)
    if dt.is_singleton:
        result["is_singleton"] = True
    return result


@mcp_tool(
    "get_list",
    title="List records",
    description=(
        "Query records of a DocType with filters, field selection, sorting and paging. "
        "Returns {data: [...], meta: {total, page, ...}}; use meta.total to count. " + _FILTERS_HELP
    ),
    input_schema={
        "type": "object",
        "properties": {
            "doctype": _DOCTYPE_ARG,
            "filters": {"type": "object", "description": _FILTERS_HELP},
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fieldnames to return; default is the list-view fields.",
            },
            "search": {"type": "string", "description": "Free-text search in search fields."},
            "order_by": {"type": "string", "description": "Sort field (default modified_at)."},
            "order": {"type": "string", "enum": ["asc", "desc"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT, "default": 20},
            "page": {"type": "integer", "minimum": 1, "default": 1},
        },
        "required": ["doctype"],
    },
    read_only=True,
)
async def get_list(
    doctype: str,
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    search: str | None = None,
    order_by: str | None = None,
    order: str = "desc",
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    res = await grunt.get_list(
        doctype,
        filters=filters,
        fields=fields,
        limit=max(1, min(int(limit), _MAX_LIMIT)),
        page=max(1, int(page)),
        order_by=order_by or "modified_at",
        order=order,
        search=search,
    )
    return res.to_dict()


@mcp_tool(
    "get_doc",
    title="Get record",
    description="Fetch one record by DocType and name, including its child tables.",
    input_schema={
        "type": "object",
        "properties": {
            "doctype": _DOCTYPE_ARG,
            "name": {"type": "string", "description": "The record's name (primary key)."},
        },
        "required": ["doctype", "name"],
    },
    read_only=True,
)
async def get_doc(doctype: str, name: str) -> dict[str, Any]:
    return await grunt.get_doc(doctype, name)


@mcp_tool(
    "search",
    title="Global search",
    description=(
        "Full-text search across all records the user can read. Returns "
        "[{doctype, name, display_title, module}]; open a hit with get_doc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Words to search for."},
            "doctype": {"type": "string", "description": "Restrict to one DocType."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        "required": ["query"],
    },
    read_only=True,
)
async def search(query: str, doctype: str | None = None, limit: int = 10) -> list[dict]:
    from grunt.api.v1.search import global_search

    return await global_search(q=query, doctype=doctype, limit=limit)


@mcp_tool(
    "create_doc",
    title="Create record",
    description=(
        "Create a record. 'data' maps fieldnames (see describe_doctype) to values; "
        "child tables are lists of row objects. Returns the saved record."
    ),
    input_schema={
        "type": "object",
        "properties": {"doctype": _DOCTYPE_ARG, "data": {"type": "object"}},
        "required": ["doctype", "data"],
    },
)
async def create_doc(doctype: str, data: dict[str, Any]) -> dict[str, Any]:
    return await grunt.new_doc(doctype, data)


@mcp_tool(
    "update_doc",
    title="Update record",
    description=(
        "Update fields of an existing record. 'data' holds only the fields to change; "
        "a child table given here replaces the whole table. Returns the saved record."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "doctype": _DOCTYPE_ARG,
            "name": {"type": "string"},
            "data": {"type": "object"},
        },
        "required": ["doctype", "name", "data"],
    },
)
async def update_doc(doctype: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
    return await grunt.save_doc(doctype, name, data)


@mcp_tool(
    "delete_doc",
    title="Delete record",
    description=(
        "Delete a record. Most DocTypes keep a restorable copy in Deleted Documents, "
        "but treat deletion as permanent and confirm with the user first."
    ),
    input_schema={
        "type": "object",
        "properties": {"doctype": _DOCTYPE_ARG, "name": {"type": "string"}},
        "required": ["doctype", "name"],
    },
    destructive=True,
)
async def delete_doc(doctype: str, name: str) -> dict[str, Any]:
    await grunt.delete_doc(doctype, name)
    return {"deleted": True, "doctype": doctype, "name": name}
