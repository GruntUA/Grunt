"""MCP Streamable HTTP transport - ``/api/v1/mcp``.

Stateless: every POST carries one JSON-RPC message and gets a plain JSON
reply (no SSE stream, no ``Mcp-Session-Id``), which the spec allows for
servers that never push messages. Authentication is the regular API auth
(``X-Api-Key`` or ``Authorization: Bearer``) via :class:`GruntRouter`; it is
header-only, so a DNS-rebinding page cannot ride on browser credentials.
"""

from __future__ import annotations

import json

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

from grunt.api.router import GruntRouter
from grunt.config import settings
from grunt.mcp.protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    PROTOCOL_VERSIONS,
    error_response,
    handle_message,
)

router = GruntRouter()


@router.post("/mcp")
async def mcp_post(request: Request) -> Response:
    if not settings.mcp_enabled:
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    version = request.headers.get("mcp-protocol-version")
    if version and version not in PROTOCOL_VERSIONS:
        return JSONResponse(
            error_response(None, INVALID_REQUEST, f"Unsupported protocol version: {version}"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        message = json.loads(await request.body())
    except ValueError:
        return JSONResponse(
            error_response(None, PARSE_ERROR, "Parse error"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    reply = await handle_message(message)
    if reply is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return JSONResponse(reply)


@router.get("/mcp")
async def mcp_get() -> Response:
    # No server-initiated stream is offered.
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": "POST"})
