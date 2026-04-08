"""Internal helpers for GruntApp."""

from __future__ import annotations

from pathlib import Path


def _collect_template_dirs() -> list[str]:
    """Return all Jinja2 template directories in priority order.

    Search order (first match wins in Jinja2 FileSystemLoader):
    1. ``grunt_apps/<app>/templates/``     — user app templates
    2. ``grunt/core/<module>/templates/``  — framework module templates
    """
    dirs: list[str] = []

    # 1. Installed grunt apps
    for pattern in ("grunt_apps/*/templates", "grunt_apps/*/*/templates"):
        for p in sorted(Path(".").glob(pattern)):
            if p.is_dir():
                dirs.append(str(p))

    # 2. All grunt core module template directories
    _core_dir = Path(__file__).parent.parent / "core"
    for p in sorted(_core_dir.rglob("templates")):
        if p.is_dir():
            dirs.append(str(p))

    return dirs


def _format_msgprint(
    msg: str | list,
    *,
    as_list: bool = False,
    as_table: bool = False,
) -> str:
    """Format a msgprint message to an HTML string."""
    if isinstance(msg, str):
        return msg

    if as_table and msg and isinstance(msg[0], (list, tuple)):
        rows_html = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in msg
        )
        return f"<table>{rows_html}</table>"

    if as_list or isinstance(msg, list):
        items_html = "".join(f"<li>{item}</li>" for item in msg)
        return f"<ul>{items_html}</ul>"

    return str(msg)
