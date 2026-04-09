"""Scripting API — Server Script execution, Client Script delivery."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from grunt.api.router import GruntRouter
from grunt.app import grunt

router = GruntRouter(prefix="", tags=["scripting"])


# ── Client Scripts ──────────────────────────────────────────────────────


@router.get("/client-script/{doctype}")
async def get_client_scripts(
    doctype: str,
) -> dict[str, Any]:
    """Return all enabled client scripts for a DocType."""
    from grunt.core.scripting.client_script import get_client_scripts as _get

    scripts = await _get(grunt._require_session(), doctype)
    return {"data": scripts}


# ── Built-in whitelisted methods ─────────────────────────────────────────


async def _handle_builtin_method(
    method: str,
    body: dict[str, Any],
) -> dict[str, Any] | None:
    """Handle framework built-in methods called via grunt.call().

    Returns a response dict if the method is built-in, None otherwise.
    """
    if method == "get_doc":
        doctype = body.get("doctype")
        doc_id = body.get("id") or body.get("name")
        if not doctype or not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="get_doc requires 'doctype' and 'id' parameters",
            )
        doc = await grunt.get_doc(str(doctype), str(doc_id))
        return {"data": doc}

    if method == "grunt.api.v1.auth.set_user_password":
        from sqlalchemy import update as sa_update

        from grunt.core.doctypes.user.user import (
            _user_table,
            get_user_by_email,
            hash_password,
        )

        user = grunt.session
        if not user.is_superadmin and user.user != body.get("email"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")

        email = body.get("email")
        password = body.get("password")
        if not email or not password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="email та password обов'язкові"
            )
            
        session = grunt._require_session()
        target = await get_user_by_email(str(email), session)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено"
            )

        table = _user_table()
        await session.execute(
            sa_update(table)
            .where(table.c.id == target.id)
            .values(hashed_password=hash_password(str(password)))
        )
        await session.flush()
        return {"success": True}

    return None


# ── Server Script API execution ─────────────────────────────────────────


@router.post("/run-server-script")
async def run_server_script(
    request: Request,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Execute a built-in framework method or an API-type Server Script."""
    from grunt.core.scripting import server_script_runner

    try:
        method = body.get("method")
        if not method:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Method is required")
        
        params = body.get("params", {})
    except Exception:
        body = {}

    builtin_result = await _handle_builtin_method(method, body)
    if builtin_result is not None:
        return builtin_result

    session = grunt._require_session()
    script = await server_script_runner.load_api_script(session, method)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API метод '{method}' не знайдено",
        )

    params = {**dict(request.query_params), **(body or {})}
    user = grunt.session

    result = await server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params},
        trusted=script.get("trusted", False),
        user_email=user.user,
        user_roles=user.roles,
        is_superadmin=user.is_superadmin,
    )

    if not result.success:
        import structlog

        structlog.get_logger().warning(
            "server_script.api_error",
            method=method,
            error=result.error,
            output=result.output,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error,
        )

    return {
        "data": result.response,
        "output": result.output,
    }
