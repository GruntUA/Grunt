"""Scripting API — Server Script execution, Client Script delivery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_engine, get_session

router = APIRouter()


# ── Client Scripts ──────────────────────────────────────────────────────


@router.get("/client-script/{doctype}")
async def get_client_scripts(
    doctype: str,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return all enabled client scripts for a DocType."""
    from grunt.core.scripting.client_script import get_client_scripts as _get  # noqa: PLC0415

    scripts = await _get(session, doctype)
    return {"data": scripts}


# ── Built-in whitelisted methods ─────────────────────────────────────────


async def _handle_builtin_method(
    method: str,
    body: dict[str, Any],
    user: GruntUser,
    session: AsyncSession,
    engine: AsyncEngine,
) -> dict[str, Any] | None:
    """Handle framework built-in methods called via grunt.call().

    Returns a response dict if the method is built-in, None otherwise.
    """
    if method == "get_doc":
        from grunt.core.document.service import DocumentService  # noqa: PLC0415

        doctype = body.get("doctype")
        doc_id = body.get("id") or body.get("name")
        if not doctype or not doc_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="get_doc requires 'doctype' and 'id' parameters",
            )
        svc = DocumentService(session, engine)
        doc = await svc.get_document(str(doctype), str(doc_id), user)
        return {"data": doc}

    if method == "grunt.api.v1.auth.set_user_password":
        from grunt.core.doctypes.User.User import get_user_by_email, hash_password, _user_table  # noqa: PLC0415
        from sqlalchemy import update as sa_update  # noqa: PLC0415

        if not user.is_superadmin and user.email != body.get("email"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав")

        email = body.get("email")
        password = body.get("password")
        if not email or not password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email та password обов'язкові")

        target = await get_user_by_email(str(email), session)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено")

        table = _user_table()
        await session.execute(
            sa_update(table).where(table.c.id == target.id).values(hashed_password=hash_password(str(password)))
        )
        await session.flush()
        return {"success": True}

    return None


# ── Server Script API execution ─────────────────────────────────────────


@router.post("/method/{method:path}")
async def run_server_script_api(
    method: str,
    request: Request,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    engine: AsyncEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Execute a built-in framework method or an API-type Server Script."""
    from grunt.core.scripting import server_script_runner  # noqa: PLC0415

    # Parse request body first (needed for both built-ins and scripts)
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Check built-in methods before looking up server scripts
    builtin_result = await _handle_builtin_method(method, body, user, session, engine)
    if builtin_result is not None:
        return builtin_result

    script = await server_script_runner.load_api_script(session, method)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API метод '{method}' не знайдено",
        )

    params = {**dict(request.query_params), **body}

    result = await server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params},
        trusted=script.get("trusted", False),
        user_email=user.email,
        user_roles=user.roles,
        is_superadmin=user.is_superadmin,
    )

    if not result.success:
        import structlog  # noqa: PLC0415
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
