"""Scripting whitelisted methods."""

from typing import Any

import grunt
from grunt.api.context import whitelist
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_session
from grunt.scripting import server_script_runner
from grunt.scripting.client_script import get_client_scripts as _get


@whitelist()
async def get_client_scripts(doctype: str) -> list[dict[str, Any]]:
    """Return all enabled client scripts for a DocType."""
    return await _get(require_session(), doctype)


@whitelist()
async def run_server_script(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Server Script of type 'API'."""
    session = require_session()
    script = await server_script_runner.load_api_script(session, method)
    if not script:
        throw(_("API method “%(method)s” not found") % {"method": method}, "NOT_FOUND")

    user = grunt.get_user()
    result = await server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params or {}},
        trusted=script.get("trusted", False),
        user_email=user.email,
        user_roles=user.role_names,
    )

    if not result.success:
        throw(result.error or "Unknown error in server script", "SCRIPT_ERROR")

    return {"response": result.response, "output": result.output}
