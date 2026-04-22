"""Jinja template rendering helpers for Grunt."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grunt.utils.app_helpers import _collect_template_dirs


async def render_template(
    app: Any,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    autoescape: bool = True,
) -> str:
    """Render a Jinja2 template using current Grunt app/session context."""
    from jinja2 import DictLoader, Environment, FileSystemLoader, select_autoescape  # noqa: PLC0415

    ctx = context or {}
    file_extensions = (".html", ".txt", ".md", ".xml", ".jinja", ".j2")
    is_file = any(template.endswith(ext) for ext in file_extensions)

    env = Environment(
        loader=FileSystemLoader(_collect_template_dirs())
        if is_file
        else DictLoader({"_": template}),
        autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
        enable_async=True,
    )

    # Globals available in every grunt template — mirrors Frappe's Jinja API.
    env.globals.update(
        {
            "grunt": app,
            "session": app.session,
            "_": app._,
            "now": datetime.now(UTC),
        }
    )

    tpl = env.get_template(template if is_file else "_")
    return await tpl.render_async(**ctx)
