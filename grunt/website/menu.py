"""Site menus — WebsiteMenuItem trees, ready for templates.

Templates call ``website_menu("main")`` (a Jinja global, see
:mod:`grunt.website.router`) and get nested dicts::

    {"label", "url", "open_in_new_tab", "icon", "highlight", "children": [...]}

``url`` is final: an item pointing at a document gets that document's page
address (its controller's ``get_web_url`` or the web view route, see
:mod:`grunt.website.generator`), so renaming a page doesn't break the menu.
Items whose document has no public page drop to ``url=None`` (rendered as a
plain heading). Disabled items hide with their whole subtree.

Built trees are cached per menu for a short while; saving or deleting an item
invalidates this process's cache (other processes catch up on expiry).
"""

from __future__ import annotations

import time
from typing import Any

from grunt.log import log

DOCTYPE = "WebsiteMenuItem"
_TTL = 60.0
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def invalidate() -> None:
    _cache.clear()


async def get_menu(menu: str = "main") -> list[dict[str, Any]]:
    cached = _cache.get(menu)
    if cached and time.monotonic() - cached[0] < _TTL:
        return cached[1]
    try:
        tree = await _build(menu)
    except Exception as exc:  # a broken menu must not take the page down
        log.warning("website.menu.error", menu=menu, error=str(exc))
        tree = []
    _cache[menu] = (time.monotonic(), tree)
    return tree


async def _build(menu: str) -> list[dict[str, Any]]:
    from grunt.app import grunt

    rows = await grunt.db.get_all(
        DOCTYPE,
        filters={"menu": menu, "enabled": 1},
        fields=[
            "name",
            "label",
            "parent_menu_item",
            "sequence",
            "url",
            "link_doctype",
            "link_name",
            "open_in_new_tab",
            "icon",
            "highlight",
        ],
        order_by="sequence",
        order="asc",
        limit=None,
    )
    urls = await _document_urls(rows)

    nodes = {
        row["name"]: {
            "label": row["label"],
            "url": urls.get((row["link_doctype"], row["link_name"]))
            if row.get("link_doctype")
            else (row.get("url") or None),
            "open_in_new_tab": bool(row.get("open_in_new_tab")),
            "icon": row.get("icon"),
            "highlight": bool(row.get("highlight")),
            "children": [],
        }
        for row in rows
    }
    roots: list[dict[str, Any]] = []
    for row in rows:  # already ordered by sequence
        parent = row.get("parent_menu_item")
        if not parent:
            roots.append(nodes[row["name"]])
        elif parent in nodes:  # a disabled parent hides its subtree
            nodes[parent]["children"].append(nodes[row["name"]])
    return roots


async def _document_urls(rows: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """(doctype, name) → public page URL, one query per linked DocType."""
    from grunt.app import grunt
    from grunt.document.registry import document_registry
    from grunt.website.generator import web_url

    wanted: dict[str, set[str]] = {}
    for row in rows:
        if row.get("link_doctype") and row.get("link_name"):
            wanted.setdefault(row["link_doctype"], set()).add(row["link_name"])

    urls: dict[tuple[str, str], str] = {}
    for doctype, names in wanted.items():
        dt = await grunt.get_meta(doctype)
        if dt is None:
            continue
        custom = getattr(document_registry.get(doctype), "get_web_url", None)
        docs = await grunt.db.get_all(doctype, filters={"name__in": sorted(names)}, limit=None)
        for doc in docs:
            url = custom(doc) if custom is not None else web_url(dt, doc)
            if url:
                urls[(doctype, doc["name"])] = url
    return urls
