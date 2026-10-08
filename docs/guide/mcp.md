# MCP server (AI agents)

Grunt ships a [Model Context Protocol](https://modelcontextprotocol.io) server, so
AI agents (Claude Code, Claude Desktop, any MCP client) can read and edit Grunt
data through the same permission checks as the UI.

- Endpoint: `POST /api/v1/mcp` (Streamable HTTP, stateless JSON replies)
- Auth: `X-Api-Key: grnt_…` (recommended) or `Authorization: Bearer <jwt>`
- Every tool runs **as the key's user**: DocType RBAC, row-level rules and
  permission-hidden fields all apply. Give agents a dedicated user with only
  the roles they need.
- Disable with `MCP_ENABLED=false`.

## Connecting a client

Create an API key for the agent's user (Desk → API Key), then e.g. for Claude Code:

```bash
claude mcp add --transport http grunt https://your-site.example.com/api/v1/mcp \
  --header "X-Api-Key: grnt_xxxxxxxx"
```

## Core tools

| Tool | What it does |
|------|--------------|
| `list_doctypes` | DocTypes the user can read (`module`, `search` filters) |
| `describe_doctype` | Fields, types, Select options, Link/Table targets, child-table fields |
| `get_list` | Filtered, sorted, paged query; `meta.total` gives the count |
| `get_doc` | One record with its child tables |
| `search` | Global full-text search |
| `create_doc` / `update_doc` | Write records (controllers and hooks run as usual) |
| `delete_doc` | Delete a record (marked destructive) |

`get_list` filters use the `grunt.db` syntax: `{"status": "Open", "amount__gte": 10}`.

## Adding tools from an app

Write an async function, decorate it with `@mcp_tool`, and list it in the app's `hooks.py`:

```python
# hrm/mcp.py
import grunt
from grunt.mcp import mcp_tool


@mcp_tool(
    "hrm_leave_balance",
    description="Remaining leave days of an employee for the current year.",
    input_schema={
        "type": "object",
        "properties": {"employee": {"type": "string", "description": "Employee name"}},
        "required": ["employee"],
    },
    read_only=True,
)
async def leave_balance(employee: str) -> dict:
    emp = await grunt.get_doc("Employee", employee)  # permission-checked
    ...
```

```python
# hrm/hooks.py
mcp_tools = ["hrm.mcp.leave_balance"]
```

Rules of thumb:

- Prefix tool names with the app name; names are `[A-Za-z0-9_.-]`, max 128 chars.
- The description is what the model reads to decide when to call the tool. Be specific.
- Raise errors with `grunt.throw(...)`. The model receives the message (`isError`) and
  the request's transaction is rolled back.
- Return JSON-serialisable data (dicts, lists, dates, Decimals are fine).
