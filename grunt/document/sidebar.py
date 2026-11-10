"""Document sidebar content from ``sidebar_sections`` in an app's ``hooks.py``.

A section is data, not a component - the desk renders every one the same way,
so an app adds sidebar content without shipping Vue. The framework's own
properties (status, ID, web page) come through here too, from
:mod:`grunt.core_hooks`::

    sidebar_sections = [
        {
            "name": "leave_balance",
            "label": "Leave balance",
            "method": "hrm.sidebar.leave_balance",
            "doctypes": ["Employee"],  # omitted - every DocType
            "roles": ["HR Manager"],  # omitted - everyone who can read the document
            "placement": "properties",  # omitted - "section"
            "order": 60,  # omitted - 50; lower comes first
        },
    ]

``method(doctype, doc_id, doc)`` is awaited with the already permission-checked
document and returns the rows, or ``None``/``[]`` to hide the section. A row is
``{"label", "value", "link"?, "external"?, "indicator"?, "copy"?, "mono"?,
"tooltip"?, "datetime"?}``: ``link`` is a desk path or URL (``external`` opens a path in a
new tab - a website page, not a desk route), ``indicator`` one of the status
colours (green, red, orange, yellow, blue, gray, success, danger, ...), ``copy``
adds a copy-to-clipboard button, ``mono`` sets the value in a monospace font,
``datetime`` (ISO) adds that moment after the value, relative ("in 3 hours"),
in the reader's language and time zone.

``placement="section"`` draws the rows under their own heading below the
built-in blocks; ``"properties"`` merges them, without a heading, into the
property list at the top of the sidebar. Registering a ``name`` that already
exists replaces that section - an app can override a core one.
A section that raises is logged and left out - it never breaks the sidebar.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import grunt
from grunt.i18n import _
from grunt.log import log
from grunt.metadata.registry import doctype_registry
lazy from grunt.i18n.service import translation_service
lazy from grunt.website.generator import WEB_URL_KEY, with_web_url
lazy from grunt.website.preview import PREVIEW_URL_KEY
lazy from grunt.workflow.registry import get_active_workflow

_ROW_KEYS = (
    "label",
    "value",
    "link",
    "external",
    "indicator",
    "copy",
    "mono",
    "tooltip",
    "datetime",
)

Placement = Literal["properties", "section"]
PLACEMENTS: tuple[Placement, ...] = ("properties", "section")


@dataclass(frozen=True)
class SidebarSection:
    name: str
    label: str
    method: Callable[..., Any]
    doctypes: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    app: str = ""
    placement: Placement = "section"
    order: int = 50


_SECTIONS: dict[str, SidebarSection] = {}


def register_sidebar_section(section: SidebarSection) -> None:
    """Add (or, by ``name``, replace) a section - a reloaded app re-registers its own."""
    if section.placement not in PLACEMENTS:
        raise ValueError(f"placement must be one of {PLACEMENTS}, got {section.placement!r}")
    _SECTIONS[section.name] = section


def sections_for(doctype: str) -> list[SidebarSection]:
    user = grunt.get_user()
    applicable = [
        s
        for s in _SECTIONS.values()
        if (not s.doctypes or doctype in s.doctypes) and (not s.roles or user.has_role(*s.roles))
    ]
    # Stable: equal orders keep registration order (core first, then apps).
    return sorted(applicable, key=lambda s: s.order)


async def collect_sections(doctype: str, doc_id: str, doc: Any) -> dict[str, list[Any]]:
    """``{"properties": [row, ...], "sections": [section, ...]}`` for this document."""
    properties: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    for s in sections_for(doctype):
        try:
            rows = s.method(doctype, doc_id, doc)
            if inspect.isawaitable(rows):
                rows = await rows
        except Exception as e:
            log.warning("sidebar.section_error", section=s.name, app=s.app, error=str(e))
            continue
        rows = [{k: r[k] for k in _ROW_KEYS if r.get(k) is not None} for r in rows or []]
        if not rows:
            continue
        if s.placement == "properties":
            properties.extend(rows)
        else:
            sections.append({"name": s.name, "label": _(s.label), "rows": rows})
    return {"properties": properties, "sections": sections}


# Core properties (registered in grunt.core_hooks)


async def status_rows(doctype: str, doc_id: str, doc: Any) -> list[dict[str, Any]]:
    """Status and, when it lives in another field, the workflow state - as badges."""
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        return []
    indicators = {i.value: i for i in meta.doc.status_indicators}

    def badge(label: str, value: Any) -> dict[str, Any] | None:
        if value is None or value == "":
            return None
        ind = indicators.get(str(value))
        text = (ind and ind.label) or str(value)
        return {
            "label": label,
            "value": translation_service.pgettext(f"status:{doctype}", text),
            "indicator": (ind and ind.color) or "default",
        }

    status_field = meta.doc.status_field or "status"
    rows = [badge(_("Status"), doc.get(status_field))]
    workflow = await get_active_workflow(doctype)
    state_field = workflow.state_field if workflow else None
    # The form hides the state field; its transitions are in the form header.
    if state_field and state_field != status_field:
        rows.append(badge(_("State"), doc.get(state_field)))
    return [r for r in rows if r]


def id_row(doctype: str, doc_id: str, doc: Any) -> list[dict[str, Any]]:
    return [{"label": "ID", "value": doc_id, "copy": True, "mono": True}]


async def web_page_row(doctype: str, doc_id: str, doc: Any) -> list[dict[str, Any]]:
    """Where the document is published (web view, WebPage, WebForm) - or, for
    a draft of a page, where to preview it."""
    # A copy: with_web_url adds the key in place.
    urls = await with_web_url(doctype, dict(getattr(doc, "data", doc)))
    if url := urls.get(WEB_URL_KEY):
        label, value = _("On website"), url
    elif url := urls.get(PREVIEW_URL_KEY):
        label, value = _("Preview"), _("Not published - open preview")
    else:
        return []
    return [
        {
            "label": label,
            "value": value,
            "link": url,
            "external": True,
            "mono": url == value,
            "tooltip": url,
        }
    ]
