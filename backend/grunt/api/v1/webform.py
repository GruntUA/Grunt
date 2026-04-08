"""Web Form API — public endpoints for form rendering and submission."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from grunt.core.db.session import get_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def _extract_user_email(request: Request, session: AsyncSession) -> str | None:
    """Try to extract user email from Authorization header (optional, no error on failure)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        import jwt  # noqa: PLC0415

        from grunt.config import settings  # noqa: PLC0415
        from grunt.core.auth.service import get_user_by_email  # noqa: PLC0415

        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email = payload.get("sub")
        if email:
            user = await get_user_by_email(email, session)
            if user and user.is_active:
                return user.email
    except Exception as exc:
        logging.getLogger(__name__).debug(
            "Failed to extract user email from Authorization header: %s",
            exc,
        )
    return None


@router.get("/webform/{route}")
async def get_web_form(
    route: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Load a published web form definition (public, no auth required)."""
    from grunt.core.webform import web_form_service  # noqa: PLC0415

    form = await web_form_service.get_form(session, route)
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Форму не знайдено",
        )

    fields = await web_form_service.get_form_fields(session, route)
    return {"data": {**form, "field_definitions": fields}}


@router.post("/webform/{route}/submit")
async def submit_web_form(
    route: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Submit a web form (public, no auth required unless login_required)."""
    from grunt.core.webform import web_form_service  # noqa: PLC0415
    from grunt.core.webform.service import WebFormError  # noqa: PLC0415

    try:
        body = await request.json()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невалідний JSON",
        ) from err

    user_email = await _extract_user_email(request, session)

    try:
        result = await web_form_service.submit(
            session=session,
            route=route,
            data=body,
            user_email=user_email,
        )
        return {"data": result}
    except WebFormError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
