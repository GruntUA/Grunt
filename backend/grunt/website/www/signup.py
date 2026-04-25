from __future__ import annotations

from typing import Any


async def get_context(context: dict[str, Any]) -> dict[str, Any]:
    context["title"] = "Реєстрація — Ґрунт"
    context["template_name"] = "_spa.html"
    return context
