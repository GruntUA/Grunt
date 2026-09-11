"""Document Connections — the "Links" tab / dashboard.

A DocType declares related document types via its ``links`` child table
(:class:`grunt.metadata.doctype.DocTypeLink`). For a given document this
service returns, per declared link, a live count and a short preview of the
documents on the other side — the data behind the form's "Зв'язки" panel and
its "+ Новий" shortcuts.

Two link shapes are supported:

* **direct** — ``link_doctype`` has a Link field ``link_fieldname`` pointing
  back at this document;
* **via child table** — ``parent_doctype`` (a child DocType) has the Link
  field ``link_fieldname``; the documents shown are the ``link_doctype``
  parents that own a matching child row. ``table_fieldname`` optionally pins
  which Table field on ``link_doctype`` holds those rows.

The ``links`` table is authoritative: a DocType that declares no rows shows
no connection chips. Backlinks are never derived from reverse Link fields.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import distinct, func, select

import grunt
from grunt.document.meta import Meta
from grunt.metadata.doctype import DocTypeLink
from grunt.metadata.registry import doctype_registry

logger = structlog.get_logger()

_PREVIEW_LIMIT = 5


async def _child_link_stats(
    link: DocTypeLink, doc_name: str
) -> tuple[int, list[dict[str, Any]]]:
    """Count + preview for a via-child-table link."""
    from grunt.app import grunt as grunt_app

    session = grunt_app._require_session()
    child_dt = await doctype_registry.get(link.parent_doctype or "")
    child_table = Meta(child_dt).table

    if link.link_fieldname not in child_table.c:
        return 0, []

    where = [child_table.c[link.link_fieldname] == doc_name]
    if link.table_fieldname and "parent_field" in child_table.c:
        where.append(child_table.c.parent_field == link.table_fieldname)

    parents_subq = select(distinct(child_table.c.parent_name)).where(*where)
    total = await session.scalar(select(func.count()).select_from(parents_subq.subquery())) or 0

    parent_names = (
        (await session.execute(parents_subq.limit(_PREVIEW_LIMIT))).scalars().all()
    )
    preview = await _resolve_titles(link.link_doctype, list(parent_names))
    return int(total), preview


async def _direct_link_stats(
    link: DocTypeLink, doc_name: str
) -> tuple[int, list[dict[str, Any]]]:
    """Count + preview for a direct reverse-Link link."""
    filters = {link.link_fieldname: doc_name}
    total = await grunt.count(link.link_doctype, filters=filters)

    link_dt = await doctype_registry.get(link.link_doctype)
    title_field = link_dt.title_field or "name"
    fields = ["name"] if title_field == "name" else ["name", title_field]
    rows = await grunt.get_list(
        link.link_doctype,
        filters=filters,
        fields=fields,
        limit=_PREVIEW_LIMIT,
        order_by="modified_at",
        order="desc",
    )
    preview = [
        {"name": r["name"], "title": r.get(title_field) or r["name"]}
        for r in rows
    ]
    return int(total), preview


async def _resolve_titles(doctype: str, names: list[str]) -> list[dict[str, Any]]:
    if not names:
        return []
    dt = await doctype_registry.get(doctype)
    title_field = dt.title_field or "name"
    fields = ["name"] if title_field == "name" else ["name", title_field]
    rows = await grunt.get_list(
        doctype, filters={"name__in": names}, fields=fields, limit=len(names)
    )
    by_name = {r["name"]: (r.get(title_field) or r["name"]) for r in rows}
    return [{"name": n, "title": by_name.get(n, n)} for n in names]


@grunt.whitelist()
async def get_connections(doctype: str, doc_id: str) -> dict[str, Any]:
    """Return grouped connection stats for one document.

    Shape::

        {
          "groups": [
            {"name": "", "links": [
              {"link_doctype": "IssueOrder", "label": "Видатковий ордер",
               "fieldname": "asset", "via_child": false, "count": 3,
               "preview": [{"name": "IO-0001", "title": "…"}], "filter_key": "asset"}
            ]}
          ]
        }
    """
    from grunt.app import grunt as grunt_app

    doc = await grunt_app.get_doc(doctype, doc_id)  # permission check
    doc_name = doc.get("name") or doc_id

    dt = await doctype_registry.get(doctype)
    # The `links` table is authoritative. A DocType that declares no rows shows
    # no connection chips — backlinks are never derived from reverse Link fields.
    links = [link for link in (dt.links or []) if not link.hidden]

    groups: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        try:
            if link.parent_doctype:
                count, preview = await _child_link_stats(link, doc_name)
            else:
                count, preview = await _direct_link_stats(link, doc_name)
        except Exception:
            logger.exception(
                "connections.link_error", doctype=doctype, link_doctype=link.link_doctype
            )
            continue

        link_dt = await doctype_registry.get(link.link_doctype)
        groups.setdefault(link.group or "", []).append(
            {
                "link_doctype": link.link_doctype,
                "label": link.label or link_dt.label or link.link_doctype,
                "fieldname": link.link_fieldname,
                "via_child": bool(link.parent_doctype),
                "count": count,
                "preview": preview,
            }
        )

    return {
        "groups": [
            {"name": name, "links": items} for name, items in groups.items()
        ]
    }
