"""MCP server at /api/v1/mcp - JSON-RPC protocol, auth and the core tools."""

from __future__ import annotations

import json

import pytest

URL = "/api/v1/mcp"

MCP_DOCTYPE = {
    "name": "McpItem",
    "label": "MCP Item",
    "module": "core",
    "description": "A record used by MCP tests",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text", "required": True},
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "Draft\nActive",
            "default": "Draft",
        },
        {"fieldname": "sb", "label": "More", "fieldtype": "Section"},
        {"fieldname": "count", "label": "Count", "fieldtype": "Int"},
    ],
    "search_fields": ["title"],
    "permissions": [
        {"role": "System Manager", "read": True, "write": True, "create": True, "delete": True},
        {"role": "Reader", "read": True},
    ],
}


@pytest.fixture
async def mcp_doctype(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**MCP_DOCTYPE, "__is_new": True})
    await ctx.db._session().commit()


async def rpc(client, headers, method, params=None, *, msg_id=1):
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        body["params"] = params
    r = await client.post(URL, json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def call(client, headers, tool, **arguments):
    """Call a tool; return (is_error, decoded payload or error text)."""
    reply = await rpc(client, headers, "tools/call", {"name": tool, "arguments": arguments})
    result = reply["result"]
    text = result["content"][0]["text"]
    if result["isError"]:
        return True, text
    return False, json.loads(text)


# ── Protocol ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_auth(client):
    r = await client.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_initialize_negotiates_version(client, auth_headers):
    reply = await rpc(client, auth_headers, "initialize", {"protocolVersion": "2025-06-18"})
    result = reply["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "grunt"
    assert "tools" in result["capabilities"]

    reply = await rpc(client, auth_headers, "initialize", {"protocolVersion": "1999-01-01"})
    assert reply["result"]["protocolVersion"] == "2025-11-25"


@pytest.mark.asyncio
async def test_notification_is_accepted_without_body(client, auth_headers):
    r = await client.post(
        URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=auth_headers,
    )
    assert r.status_code == 202
    assert r.content == b""


@pytest.mark.asyncio
async def test_bad_requests(client, auth_headers):
    r = await client.post(URL, content=b"{not json", headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32700

    r = await client.post(
        URL,
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={**auth_headers, "MCP-Protocol-Version": "1999-01-01"},
    )
    assert r.status_code == 400

    reply = await rpc(client, auth_headers, "resources/list")
    assert reply["error"]["code"] == -32601

    reply = await rpc(client, auth_headers, "tools/call", {"name": "no_such_tool"})
    assert reply["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_get_is_not_allowed(client, auth_headers):
    r = await client.get(URL, headers=auth_headers)
    assert r.status_code == 405


@pytest.mark.asyncio
async def test_tools_list(client, auth_headers):
    reply = await rpc(client, auth_headers, "tools/list")
    tools = {t["name"]: t for t in reply["result"]["tools"]}
    assert {
        "list_doctypes",
        "describe_doctype",
        "get_list",
        "get_doc",
        "search",
        "create_doc",
        "update_doc",
        "delete_doc",
    } <= set(tools)
    assert tools["get_list"]["annotations"]["readOnlyHint"] is True
    assert tools["delete_doc"]["annotations"]["destructiveHint"] is True
    assert tools["get_doc"]["inputSchema"]["required"] == ["doctype", "name"]


# ── Tools ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discovery(client, auth_headers, mcp_doctype):
    err, doctypes = await call(client, auth_headers, "list_doctypes", search="mcp item")
    assert not err
    assert [d["name"] for d in doctypes] == ["McpItem"]
    assert doctypes[0]["description"] == "A record used by MCP tests"

    err, meta = await call(client, auth_headers, "describe_doctype", doctype="McpItem")
    assert not err
    fields = {f["fieldname"]: f for f in meta["fields"]}
    assert "sb" not in fields  # layout-only
    assert fields["title"]["required"] is True
    assert fields["status"]["options"] == ["Draft", "Active"]
    assert fields["status"]["default"] == "Draft"


@pytest.mark.asyncio
async def test_crud_round_trip(client, auth_headers, mcp_doctype):
    err, doc = await call(
        client, auth_headers, "create_doc", doctype="McpItem", data={"title": "Alpha", "count": 3}
    )
    assert not err, doc
    name = doc["name"]

    err, page = await call(
        client,
        auth_headers,
        "get_list",
        doctype="McpItem",
        filters={"count__gte": 2},
        fields=["name", "title"],
    )
    assert not err
    assert page["meta"]["total"] == 1
    assert page["data"][0]["title"] == "Alpha"

    err, doc = await call(
        client, auth_headers, "update_doc", doctype="McpItem", name=name, data={"status": "Active"}
    )
    assert not err
    assert doc["status"] == "Active"

    err, doc = await call(client, auth_headers, "get_doc", doctype="McpItem", name=name)
    assert not err
    assert (doc["title"], doc["status"]) == ("Alpha", "Active")

    err, res = await call(client, auth_headers, "delete_doc", doctype="McpItem", name=name)
    assert not err
    assert res["deleted"] is True

    err, text = await call(client, auth_headers, "get_doc", doctype="McpItem", name=name)
    assert err
    assert "NOT_FOUND" in text or "404" in text


@pytest.mark.asyncio
async def test_tool_errors_are_reported_to_model(client, auth_headers, mcp_doctype):
    err, text = await call(client, auth_headers, "describe_doctype", doctype="NoSuchType")
    assert err

    err, text = await call(client, auth_headers, "get_doc", doctype="McpItem")
    assert err
    assert "name" in text

    err, text = await call(client, auth_headers, "get_doc", doctype="McpItem", name="x", y=1)
    assert err
    assert "Unknown arguments" in text

    # Validation failure (missing required field) leaves nothing behind.
    err, text = await call(client, auth_headers, "create_doc", doctype="McpItem", data={})
    assert err
    err, page = await call(client, auth_headers, "get_list", doctype="McpItem")
    assert page["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_disabled(client, auth_headers, monkeypatch):
    from grunt.config import settings

    monkeypatch.setattr(settings, "mcp_enabled", False)
    r = await client.post(
        URL, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=auth_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tools_act_with_callers_permissions(ctx, db_session, engine, mcp_doctype):
    import grunt
    from grunt.mcp.protocol import handle_message
    from tests.support import make_user

    async def tool(user, name, **arguments):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        async with grunt.context(db_session, engine, user):
            return (await handle_message(msg))["result"]

    reader = make_user("reader@grunt.example.com", roles=["Reader"])
    nobody = make_user("nobody@grunt.example.com", roles=[])

    names = json.loads(
        (await tool(reader, "list_doctypes", search="McpItem"))["content"][0]["text"]
    )
    assert [d["name"] for d in names] == ["McpItem"]
    names = json.loads(
        (await tool(nobody, "list_doctypes", search="McpItem"))["content"][0]["text"]
    )
    assert names == []

    result = await tool(reader, "create_doc", doctype="McpItem", data={"title": "Nope"})
    assert result["isError"]
    assert "FORBIDDEN" in result["content"][0]["text"]

    result = await tool(nobody, "describe_doctype", doctype="McpItem")
    assert result["isError"]


# ── Registry ─────────────────────────────────────────────────────────────


def test_registry_rejects_bad_and_duplicate_names():
    from grunt.mcp import McpTool, register_tool

    async def handler() -> None: ...

    with pytest.raises(ValueError):
        register_tool(McpTool(name="bad name!", description="", handler=handler))
    with pytest.raises(ValueError):
        register_tool(McpTool(name="get_doc", description="", handler=handler))
