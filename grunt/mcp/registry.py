"""MCP tool registry - what the ``/api/v1/mcp`` endpoint exposes.

A tool is an async function plus the metadata an MCP client needs to call it
(name, description, JSON Schema of its arguments, behaviour hints). Register
one with :func:`mcp_tool`; apps list their tool functions in ``hooks.py``
(``mcp_tools = ["hrm.mcp.leave_balance"]``) so they are imported on load.

Tools run inside the caller's grunt context, as the authenticated user, so
everything they call through the SDK is permission-checked as usual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    ToolHandler = Callable[..., Awaitable[Any]]

# MCP spec: tool names are 1-128 chars of [A-Za-z0-9_.-].
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


@dataclass(frozen=True, slots=True)
class McpTool:
    name: str
    description: str
    handler: ToolHandler
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    title: str | None = None
    read_only: bool = False
    destructive: bool = False

    def describe(self) -> dict[str, Any]:
        """The tool as a ``tools/list`` entry."""
        info: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
                "openWorldHint": False,
            },
        }
        if self.title:
            info["title"] = self.title
            info["annotations"]["title"] = self.title
        return info


_TOOLS: dict[str, McpTool] = {}


def register_tool(tool: McpTool) -> None:
    """Add *tool* to the registry; re-registering the same function is a no-op."""
    if not _NAME_RE.match(tool.name):
        raise ValueError(f"Invalid MCP tool name {tool.name!r}")
    existing = _TOOLS.get(tool.name)
    if existing is not None and existing.handler.__qualname__ != tool.handler.__qualname__:
        raise ValueError(f"MCP tool {tool.name!r} is already registered")
    _TOOLS[tool.name] = tool


def mcp_tool(
    name: str | None = None,
    *,
    description: str | None = None,
    input_schema: dict[str, Any] | None = None,
    title: str | None = None,
    read_only: bool = False,
    destructive: bool = False,
) -> Callable[[ToolHandler], ToolHandler]:
    """Expose an async function as an MCP tool.

    ``description`` defaults to the docstring - it is what the model reads to
    decide when to call the tool, so make it specific. App tools should carry
    the app name as a prefix (``hrm_leave_balance``) to avoid collisions::

        @mcp_tool(
            "hrm_leave_balance",
            input_schema={
                "type": "object",
                "properties": {"employee": {"type": "string"}},
                "required": ["employee"],
            },
            read_only=True,
        )
        async def leave_balance(employee: str) -> dict: ...
    """

    def decorator(fn: ToolHandler) -> ToolHandler:
        register_tool(
            McpTool(
                name=name or fn.__name__,
                description=(description or fn.__doc__ or "").strip(),
                handler=fn,
                input_schema=input_schema or {"type": "object", "properties": {}},
                title=title,
                read_only=read_only,
                destructive=destructive,
            )
        )
        return fn

    return decorator


def get_tool(name: str) -> McpTool | None:
    return _TOOLS.get(name)


def list_tools() -> list[McpTool]:
    return list(_TOOLS.values())
