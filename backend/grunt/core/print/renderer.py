"""Print template renderer using Jinja2."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

from grunt.core.print.filters import JINJA_FILTERS

logger = structlog.get_logger()

# Template search paths: app templates + core templates
_TEMPLATE_DIRS: list[Path] = []


def _get_template_dirs() -> list[str]:
    """Collect all template directories from installed apps."""
    dirs: list[str] = []
    apps_dir = Path("grunt-apps")
    if apps_dir.exists():
        for tpl_dir in apps_dir.glob("*/*/templates"):
            dirs.append(str(tpl_dir))
    # Core templates as fallback
    core_tpl = Path(__file__).parent / "templates"
    if core_tpl.exists():
        dirs.append(str(core_tpl))
    return dirs


def render_template(template_name: str, doc: dict[str, Any]) -> str:
    """Render a Jinja2 print template with document data."""
    dirs = _get_template_dirs()
    if not dirs:
        raise FileNotFoundError(f"No template directories found for '{template_name}'")

    env = Environment(
        loader=FileSystemLoader(dirs),
        autoescape=select_autoescape(["html"]),
    )
    env.filters.update(JINJA_FILTERS)

    template = env.get_template(template_name)
    return template.render(doc=doc, now=datetime.now(timezone.utc))
