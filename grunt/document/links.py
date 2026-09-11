"""Document Links service — automatic backlinks between documents.

When a document with a Link field is saved, backlinks are created/updated
in the grunt_doc_link table. This allows querying "which documents reference
this one" efficiently.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, select

from grunt.log import log
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _child_owner_map(all_dts: list[Any]) -> dict[str, str]:
    """child DocType name -> first parent DocType that embeds it via a Table field."""
    owner: dict[str, str] = {}
    for dt in all_dts:
        for field in dt.fields:
            if field.fieldtype == "Table" and field.options:
                owner.setdefault(field.options, dt.name)
    return owner


class LinkService:
    """Manages document backlinks."""

    async def sync_links(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
        doc: dict[str, Any],
    ) -> int:
        """Sync document links after a save — delete old links, insert new ones.

        Scans all Link fields in the DocType and creates backlink records
        for any non-empty Link values.

        Returns the number of links created.
        """
        from grunt.metadata.compiler import compile_doctype_to_table

        doclink_dt = await doctype_registry.get("DocLink")
        table = compile_doctype_to_table(doclink_dt)
        dt = await doctype_registry.get(doctype)

        # Delete existing links from this source document
        await session.execute(
            delete(table).where(
                and_(
                    table.c.source_doctype == doctype,
                    table.c.source_id == doc_id,
                )
            )
        )

        # Find all Link fields and create new backlinks
        count = 0
        for field in dt.fields:
            if field.fieldtype != "Link":
                continue
            target_id = doc.get(field.fieldname)
            if not target_id:
                continue
            target_doctype = field.options  # Link field's options = target DocType
            if not target_doctype:
                continue

            link_name = f"{doctype}-{doc_id}-{field.fieldname}"
            from datetime import datetime

            now = datetime.now(UTC)
            await session.execute(
                table.insert().values(
                    name=link_name,
                    owner="system",
                    created_at=now,
                    modified_at=now,
                    modified_by="system",
                    docstatus=0,
                    source_doctype=doctype,
                    source_id=doc_id,
                    target_doctype=target_doctype,
                    target_id=str(target_id),
                    link_fieldname=field.fieldname,
                )
            )
            count += 1

        if count:
            await session.flush()
            log.debug("links.synced", doctype=doctype, doc_id=doc_id, links=count)

        return count

    async def get_backlinks(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> list[dict[str, str]]:
        """Get all documents that link to a specific document.

        Returns a list of dicts with source_doctype, source_id, link_fieldname.
        """
        from grunt.metadata.compiler import compile_doctype_to_table

        dt_doc_link = await doctype_registry.get("DocLink")
        table = compile_doctype_to_table(dt_doc_link)
        stmt = (
            select(table)
            .where(table.c.target_doctype == doctype)
            .where(table.c.target_id == doc_id)
            .order_by(table.c.source_doctype, table.c.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "source_doctype": r["source_doctype"],
                "source_id": r["source_id"],
                "link_fieldname": r["link_fieldname"],
            }
            for r in rows
        ]

    async def get_delete_impact(
        self,
        session: AsyncSession,
        doctype: str,
        doc_ids: list[str],
    ) -> dict[str, Any]:
        """Summarise what references *doc_ids* — the impact of deleting them.

        Unlike :meth:`get_backlinks` (which reads the ``DocLink`` cache, direct
        Link fields only) this scans every DocType's Link fields — including
        those inside child tables — plus MultiLink rows, and returns grouped
        counts::

            {"total": 11, "groups": [
                {"doctype": "Employee", "label": "Співробітник",
                 "field": "department", "field_label": "Відділ",
                 "count": 8, "in_child": false, "parent_doctype": null},
                {"doctype": null, "label": "Множинні зв'язки", "field": null,
                 "count": 3, "in_child": false, "parent_doctype": null},
            ]}

        References originating from the documents being deleted themselves are
        excluded — they disappear with the rows.
        """
        from grunt.document.meta import Meta

        ids = [i for i in doc_ids if i]
        if not ids:
            return {"total": 0, "groups": []}

        all_dts = await doctype_registry.list_all()
        child_owner = _child_owner_map(all_dts)

        groups: list[dict[str, Any]] = []
        total = 0

        for other_dt in all_dts:
            other_meta = Meta(other_dt)
            ref_table = other_meta.table
            in_child = bool(getattr(other_dt, "is_child", False))
            for field in other_meta.get_link_fields():
                if field.fieldtype != "Link" or field.options != doctype:
                    continue
                if field.fieldname not in ref_table.c:
                    continue
                where = [ref_table.c[field.fieldname].in_(ids)]
                # A row of the DocType itself that we're also deleting is not a
                # dangling reference — skip self-references within the batch.
                if other_dt.name == doctype and "name" in ref_table.c:
                    where.append(ref_table.c.name.notin_(ids))
                count = (
                    await session.scalar(select(func.count()).select_from(ref_table).where(*where))
                    or 0
                )
                if not count:
                    continue
                total += int(count)
                groups.append(
                    {
                        "doctype": other_dt.name,
                        "label": other_dt.label or other_dt.name,
                        "field": field.fieldname,
                        "field_label": field.label or field.fieldname,
                        "count": int(count),
                        "in_child": in_child,
                        "parent_doctype": child_owner.get(other_dt.name) if in_child else None,
                    }
                )

        # MultiLink references pointing at any of the ids.
        from grunt.metadata.compiler import MULTI_LINK_TABLE

        ml_count = (
            await session.scalar(
                select(func.count())
                .select_from(MULTI_LINK_TABLE)
                .where(
                    MULTI_LINK_TABLE.c.link_doctype == doctype,
                    MULTI_LINK_TABLE.c.link_name.in_(ids),
                    MULTI_LINK_TABLE.c.parent_name.notin_(ids),
                )
            )
            or 0
        )
        if ml_count:
            total += int(ml_count)
            groups.append(
                {
                    "doctype": None,
                    "label": "Множинні зв'язки",
                    "field": None,
                    "field_label": None,
                    "count": int(ml_count),
                    "in_child": False,
                    "parent_doctype": None,
                }
            )

        groups.sort(key=lambda g: g["count"], reverse=True)
        return {"total": total, "groups": groups}

    async def delete_links(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> None:
        """Remove all links from and to a document (on delete)."""
        from grunt.metadata.compiler import compile_doctype_to_table

        dt_doc_link = await doctype_registry.get("DocLink")
        table = compile_doctype_to_table(dt_doc_link)

        # Links FROM this document
        await session.execute(
            delete(table).where(
                and_(
                    table.c.source_doctype == doctype,
                    table.c.source_id == doc_id,
                )
            )
        )
        # Links TO this document
        await session.execute(
            delete(table).where(
                and_(
                    table.c.target_doctype == doctype,
                    table.c.target_id == doc_id,
                )
            )
        )


link_service = LinkService()
