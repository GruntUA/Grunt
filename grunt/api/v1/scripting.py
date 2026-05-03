"""Scripting whitelisted methods."""

from __future__ import annotations

from typing import Any

import grunt


@grunt.whitelist()
async def get_client_scripts(doctype: str) -> list[dict[str, Any]]:
    """Return all enabled client scripts for a DocType."""
    from grunt.app import grunt as grunt_app
    from grunt.scripting.client_script import get_client_scripts as _get

    return await _get(grunt_app._require_session(), doctype)


@grunt.whitelist()
async def run_server_script(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Server Script of type 'API'."""
    from grunt.app import grunt as grunt_app
    from grunt.scripting import server_script_runner

    session = grunt_app._require_session()
    script = await server_script_runner.load_api_script(session, method)
    if not script:
        grunt.throw(f"API метод '{method}' не знайдено", "NOT_FOUND")

    user = grunt_app._require_user()
    result = await server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params or {}},
        trusted=script.get("trusted", False),
        user_email=user.email,
        user_roles=user.roles,
        is_superadmin=user.is_superadmin,
    )

    if not result.success:
        grunt.throw(result.error or "Unknown error in server script", "SCRIPT_ERROR")

    return {"response": result.response, "output": result.output}
