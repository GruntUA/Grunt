"""App sections of the document sidebar (``sidebar_sections`` in an app's ``hooks.py``).

A section is data, not a component - the desk renders every one the same way,
so an app adds sidebar content without shipping Vue::

    sidebar_sections = [
        {
            "name": "leave_balance",
            "label": "Leave balance",
            "method": "hrm.sidebar.leave_balance",
            "doctypes": ["Employee"],  # omitted - every DocType
            "roles": ["HR Manager"],  # omitted - everyone who can read the document
        },
    ]

``method(doctype, doc_id, doc)`` is awaited with the already permission-checked
document and returns the rows, or ``None``/``[]`` to hide the section. A row is
``{"label", "value", "link"?, "indicator"?}``: ``link`` is a desk path or URL,
``indicator`` one of the status colours (green, red, orange, yellow, blue, gray).
A section that raises is logged and left out - it never breaks the sidebar.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import grunt
from grunt import _, log
from grunt.permissions.roles import user_has_roles

_ROW_KEYS = ("label", "value", "link", "indicator")


@dataclass(frozen=True)
class SidebarSection:
    name: str
    label: str
    method: Callable[..., Any]
    doctypes: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    app: str = ""


_SECTIONS: dict[str, SidebarSection] = {}


def register_sidebar_section(section: SidebarSection) -> None:
    """Add (or, by ``name``, replace) a section - a reloaded app re-registers its own."""
    _SECTIONS[section.name] = section


def sections_for(doctype: str) -> list[SidebarSection]:
    user = grunt.get_user()
    return [
        s
        for s in _SECTIONS.values()
        if (not s.doctypes or doctype in s.doctypes)
        and (not s.roles or user_has_roles(user, list(s.roles)))
    ]


async def collect_sections(doctype: str, doc_id: str, doc: Any) -> list[dict[str, Any]]:
    """The sidebar payload of every section that applies and has rows."""
    out = []
    for s in sections_for(doctype):
        try:
            rows = s.method(doctype, doc_id, doc)
            if inspect.isawaitable(rows):
                rows = await rows
        except Exception as e:
            log.warning("sidebar.section_error", section=s.name, app=s.app, error=str(e))
            continue
        rows = [{k: r[k] for k in _ROW_KEYS if r.get(k) is not None} for r in rows or []]
        if rows:
            out.append({"name": s.name, "label": _(s.label), "rows": rows})
    return out
