"""Scripting whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt
from grunt import _
from grunt.scripting import server_script_runner
from grunt.scripting.client_script import get_client_scripts as _get


@grunt.whitelist()
async def get_client_scripts(doctype: str) -> list[dict[str, Any]]:
    """Return all enabled client scripts for a DocType."""
    return await _get(grunt.get_session(), doctype)


@grunt.whitelist()
async def run_server_script(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Server Script of type 'API'."""
    session = grunt.get_session()
    script = await server_script_runner.load_api_script(session, method)
    if not script:
        grunt.throw(_("API method “%(method)s” not found") % {"method": method}, "NOT_FOUND")

    user = grunt.get_user()
    result = await server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params or {}},
        trusted=script.get("trusted", False),
        user_email=user.email,
        user_roles=user.roles,
    )

    if not result.success:
        grunt.throw(result.error or "Unknown error in server script", "SCRIPT_ERROR")

    return {"response": result.response, "output": result.output}
