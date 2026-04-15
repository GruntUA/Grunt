"""Web Form whitelisted methods."""

from __future__ import annotations
from typing import Any
import grunt

@grunt.whitelist(allow_guest=True)
async def get_form(route: str) -> dict[str, Any]:
    """Load a published web form definition (public, no auth required)."""
    from grunt.core.webform import web_form_service
    from grunt.app import grunt as grunt_app
    
    session = grunt_app._require_session()
    form = await web_form_service.get_form(session, route)
    if not form:
        grunt.throw("Форму не знайдено", "NOT_FOUND")

    fields = await web_form_service.get_form_fields(session, route)
    return {**form, "field_definitions": fields}

@grunt.whitelist(allow_guest=True)
async def submit_form(route: str, data: dict[str, Any]) -> dict[str, Any]:
    """Submit a web form."""
    from grunt.core.webform import web_form_service
    from grunt.app import grunt as grunt_app
    
    user = await grunt.get_current_user()
    user_email = user.email if user else None

    try:
        result = await web_form_service.submit(
            session=grunt_app._require_session(),
            route=route,
            data=data,
            user_email=user_email,
        )
        return result
    except Exception as e:
        grunt.throw(str(e), "SUBMISSION_ERROR")
