"""Web Form API — public endpoints for form rendering and submission."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from grunt.app import grunt

router = APIRouter(prefix="", tags=["webform"])


@router.get("/webform/{route}")
async def get_webform_api(
    route: str,
) -> dict[str, Any]:
    """Load a published web form definition (public, no auth required)."""
    from grunt.core.webform import web_form_service

    form = await web_form_service.get_form(grunt._require_session(), route)
    if not form:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Форму не знайдено",
        )

    fields = await web_form_service.get_form_fields(grunt._require_session(), route)
    return {"data": {**form, "field_definitions": fields}}


@router.post("/webform/{route}/submit")
async def submit_web_form(
    route: str,
    request: Request,
) -> dict[str, Any]:
    """Submit a web form (public, no auth required unless login_required)."""
    from grunt.core.webform import web_form_service
    from grunt.core.webform.service import WebFormError

    try:
        body = await request.json()
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невалідний JSON",
        ) from err

    user = getattr(grunt, "session", None)
    user_email = user.user if user else None

    try:
        result = await web_form_service.submit(
            session=grunt._require_session(),
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
