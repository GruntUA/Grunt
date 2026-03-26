"""Scripting API — Server Script execution, Client Script delivery."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from grunt.core.auth.dependencies import current_user
from grunt.core.auth.models import GruntUser
from grunt.core.db.session import get_session

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


# ── Server Script API execution ─────────────────────────────────────────


@router.post("/method/{method:path}")
async def run_server_script_api(
    method: str,
    request: Request,
    user: GruntUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Execute an API-type Server Script."""
    from grunt.core.scripting import server_script_runner  # noqa: PLC0415

    script = await server_script_runner.load_api_script(session, method)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API метод '{method}' не знайдено",
        )

    # Parse request body
    try:
        body = await request.json()
    except Exception:
        body = {}

    params = {**dict(request.query_params), **body}

    result = server_script_runner.execute(
        script["script"],
        session=session,
        extra_context={"params": params},
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error,
        )

    return {
        "data": result.response,
        "output": result.output,
    }
