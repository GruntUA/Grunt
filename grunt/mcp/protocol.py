"""MCP JSON-RPC dispatch (server side, tools capability only).

Transport-agnostic: :func:`handle_message` takes one decoded JSON-RPC message
and returns the response object, or ``None`` for notifications and client
responses. The HTTP transport lives in :mod:`grunt.api.v1.mcp`.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

import grunt
from grunt import log
from grunt.errors import ApplicationError
from grunt.mcp.registry import get_tool, list_tools
from grunt.storage.signing import sign_file_urls

# Newest first; the first entry is offered when the client asks for one we lack.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

SERVER_INFO = {"name": "grunt", "title": "Ґрунт", "version": "0.1.0"}

INSTRUCTIONS = (
    "Ґрунт is a metadata-driven business application platform: all data lives in "
    "records of DocTypes. Discover DocTypes with list_doctypes, read their fields with "
    "describe_doctype, then query with get_list / get_doc or search. Every call runs "
    "with the permissions of the user who owns the credentials."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _negotiate(requested: Any) -> str:
    return requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": _negotiate(params.get("protocolVersion")),
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def _to_text(value: Any) -> str:
    text = json.dumps(jsonable_encoder(value), ensure_ascii=False, default=str)
    # Private file URLs in the payload get the same short-lived signature the
    # regular JSON API adds (grunt.storage.signing).
    return sign_file_urls(text.encode()).decode()


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


async def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    tool = get_tool(name) if isinstance(name, str) else None
    if tool is None:
        raise JsonRpcError(INVALID_PARAMS, f"Unknown tool: {name}")

    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise JsonRpcError(INVALID_PARAMS, "Tool arguments must be an object")
    missing = [k for k in tool.input_schema.get("required", []) if k not in arguments]
    if missing:
        return _tool_error(f"Missing required arguments: {', '.join(missing)}")
    unknown = set(arguments) - set(tool.input_schema.get("properties", {}))
    if unknown:
        return _tool_error(f"Unknown arguments: {', '.join(sorted(unknown))}")

    # Errors are reported to the model (isError) so it can correct itself; the
    # request's session is rolled back so a failed write leaves nothing behind.
    try:
        result = await tool.handler(**arguments)
    except ApplicationError as e:
        await grunt.get_session().rollback()
        return _tool_error(f"{e.code}: {e.message}")
    except HTTPException as e:
        await grunt.get_session().rollback()
        code = getattr(e, "code", None) or str(e.status_code)
        return _tool_error(f"{code}: {e.detail}")
    except Exception:
        await grunt.get_session().rollback()
        log.exception("mcp.tool_failed", tool=tool.name)
        return _tool_error("Internal error while running the tool")

    log.info("mcp.tool_called", tool=tool.name)
    return {"content": [{"type": "text", "text": _to_text(result)}], "isError": False}


async def _dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "initialize":
        return _initialize(params)
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [t.describe() for t in list_tools()]}
    if method == "tools/call":
        return await _call_tool(params)
    raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")


async def handle_message(message: Any) -> dict[str, Any] | None:
    """Process one JSON-RPC message; ``None`` means "nothing to send back"."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return error_response(None, INVALID_REQUEST, "Invalid JSON-RPC message")

    method = message.get("method")
    if method is None:
        # A response to a server request - we never send any; ignore.
        return None
    request_id = message.get("id")
    is_notification = "id" not in message

    params = message.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        if is_notification:
            return None
        return error_response(request_id, INVALID_REQUEST, "Invalid JSON-RPC request")

    if is_notification:
        # notifications/initialized, notifications/cancelled, ... - nothing to do.
        return None

    try:
        result = await _dispatch(method, params)
    except JsonRpcError as e:
        return error_response(request_id, e.code, e.message)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
