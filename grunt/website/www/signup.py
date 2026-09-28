from __future__ import annotations

from typing import Any

from grunt.i18n import _


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    context["title"] = _("Sign up") + " — Ґрунт"
    context["template_name"] = "_spa.html"
    return context
