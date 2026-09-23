"""Web Form whitelisted methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt

if TYPE_CHECKING:
    from fastapi import Request


@grunt.whitelist(allow_guest=True)
async def get_form(route: str) -> dict[str, Any]:
    """Load a published web form definition (public, no auth required)."""
    from grunt.webform import web_form_service

    form = await web_form_service.get_form(route)
    if not form:
        grunt.throw("Форму не знайдено", "NOT_FOUND")

    fields = await web_form_service.get_form_fields(route)
    return {**form, "field_definitions": fields}


@grunt.whitelist(allow_guest=True)
async def submit_form(
    route: str,
    data: dict[str, Any],
    captcha_token: str | None = None,
    request: Request | None = None,
) -> dict[str, Any]:
    """Submit a web form.

    ``request`` is auto-injected by the dispatcher (see
    ``grunt.api.v1.method._invoke_with_context``) — never passed by a caller —
    purely to get the caller's IP for CAPTCHA verification below.
    """
    from grunt.config import settings
    from grunt.context import _user_ctx
    from grunt.webform import web_form_service
    from grunt.webform.captcha import verify_captcha

    # grunt.get_current_user() is the wrong tool here: it falls back to a
    # synthetic "system" user when no one is authenticated, so `user_email`
    # would always be truthy and web_form_service.submit()'s
    # `if form["login_required"] and not user_email` check could never
    # actually block an anonymous submission. Read the raw context instead,
    # which is genuinely None for a guest request (allow_guest=True routes
    # user=None into context rather than raising).
    user = _user_ctx.get()
    user_email = user.email if user else None

    form = await web_form_service.get_form(route)
    if form and form.get("captcha_enabled") and settings.captcha_provider:
        from grunt.auth.doctypes.UserSession.user_session import client_ip

        ip = client_ip(request) or "unknown"
        if not await verify_captcha(captcha_token, ip):
            grunt.throw("Не вдалося підтвердити, що ви не робот", "CAPTCHA_FAILED")

    try:
        result = await web_form_service.submit(route=route, data=data, user_email=user_email)
        return result
    except Exception as e:
        grunt.throw(str(e), "SUBMISSION_ERROR")
