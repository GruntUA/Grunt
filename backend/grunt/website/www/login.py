from __future__ import annotations

from typing import Any


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    context["title"] = "Вхід — Ґрунт"
    # Use the SPA template instead of a local .html file
    context["template_name"] = "_spa.html"
    return context
