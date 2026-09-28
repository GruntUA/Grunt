from __future__ import annotations

from typing import Any

from grunt import _


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    context["title"] = _("Sign in") + " — Ґрунт"
    # Use the SPA template instead of a local .html file
    context["template_name"] = "_spa.html"
    return context
