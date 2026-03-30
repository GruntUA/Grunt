"""Document Links service — automatic backlinks between documents.

When a document with a Link field is saved, backlinks are created/updated
in the grunt_doc_link table. This allows querying "which documents reference
this one" efficiently.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger()


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
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocLink"])
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

            link_id = str(uuid.uuid4())
            from datetime import datetime, timezone  # noqa: PLC0415
            now = datetime.now(timezone.utc)
            await session.execute(
                table.insert().values(
                    id=link_id,
                    name=link_id,
                    owner="system",
                    created_at=now,
                    modified_at=now,
                    modified_by="system",
                    docstatus=0,
                    source_doctype=doctype,
                    source_id=str(doc_id),
                    target_doctype=target_doctype,
                    target_id=str(target_id),
                    link_fieldname=field.fieldname,
                )
            )
            count += 1

        if count:
            await session.flush()
            logger.debug(
                "links.synced", doctype=doctype, doc_id=doc_id, links=count
            )

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
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocLink"])
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

    async def delete_links(
        self,
        session: AsyncSession,
        doctype: str,
        doc_id: str,
    ) -> None:
        """Remove all links from and to a document (on delete)."""
        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

        table = compile_doctype_to_table(doctype_registry._doctypes["DocLink"])

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
