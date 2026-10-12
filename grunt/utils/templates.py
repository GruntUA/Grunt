"""Jinja template rendering helpers for Grunt."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from grunt.i18n.jinja import install as install_i18n
from grunt.local import _user_ctx
from grunt.utils.app_helpers import _collect_template_dirs


async def render_template(
    app: Any,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    autoescape: bool = True,
) -> str:
    """Render a Jinja2 template using current Grunt app/session context."""
    from jinja2 import DictLoader, FileSystemLoader, select_autoescape
    from jinja2.sandbox import SandboxedEnvironment

    ctx = context or {}
    file_extensions = (".html", ".txt", ".md", ".xml", ".jinja", ".j2")
    is_file = any(template.endswith(ext) for ext in file_extensions)

    # Sandboxed: this helper can be handed a raw template string (the DictLoader
    # branch) and injects the whole ``grunt`` facade as a global, so a plain
    # Environment would be an SSTI -> RCE sink the moment any caller forwards
    # user input. SandboxedEnvironment blocks ``__``/private attribute access
    # and unsafe callables while leaving ordinary templating intact.
    env = SandboxedEnvironment(
        loader=FileSystemLoader(_collect_template_dirs())
        if is_file
        else DictLoader({"_": template}),
        autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
        enable_async=True,
    )

    # Globals available in every grunt template.

    env.globals["grunt"] = app
    env.globals["user"] = _user_ctx.get()  # None when rendered outside a user's context
    env.globals["now"] = datetime.now(UTC)

    install_i18n(env)

    tpl = env.get_template(template if is_file else "_")
    return await tpl.render_async(**ctx)
