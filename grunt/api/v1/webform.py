"""Web Form whitelisted methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt import _
from grunt.local import _user_ctx
from grunt.webform import web_form_service
from grunt.webform.captcha import captcha_site_key, verify_captcha

if TYPE_CHECKING:
    from fastapi import Request


@grunt.whitelist(allow_guest=True)
async def get_form(route: str) -> dict[str, Any]:
    """Load a published web form definition (public, no auth required)."""
    form = await web_form_service.get_form(route)
    if not form:
        grunt.throw(_("Form not found"), "NOT_FOUND")

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
    ``grunt.api.v1.method._invoke_with_context``) - never passed by a caller -
    purely to get the caller's IP for CAPTCHA verification below.
    """
    # A guest may submit (allow_guest=True puts user=None into context), so
    # read the context directly - grunt.get_user() would raise a 401 here.
    user = _user_ctx.get()
    user_email = user.email if user else None

    form = await web_form_service.get_form(route)
    if form and form.get("captcha_enabled") and await captcha_site_key() is not None:
        from grunt.auth.doctypes.UserSession.user_session import client_ip

        ip = client_ip(request) or "unknown"
        if not await verify_captcha(captcha_token, ip):
            grunt.throw(_("Could not verify that you are not a robot"), "CAPTCHA_FAILED")

    try:
        result = await web_form_service.submit(route=route, data=data, user_email=user_email)
        return result
    except Exception as e:
        grunt.throw(str(e), "SUBMISSION_ERROR")
