"""MultiLink service — manages many-to-many relationships via junction table."""

from __future__ import annotations

from itertools import islice
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, select

from grunt.metadata.compiler import MULTI_LINK_TABLE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class MultiLinkService:
    """Handles CRUD for MultiLink field values stored in grunt_core_multi_link."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_values(
        self,
        parent_doctype: str,
        parent_id: str,
        parent_field: str,
    ) -> list[str]:
        """Return ordered list of linked names for a single MultiLink field."""
        t = MULTI_LINK_TABLE
        result = await self.session.execute(
            select(t.c.link_name)
            .where(
                t.c.parent_doctype == parent_doctype,
                t.c.parent_name == parent_id,
                t.c.parent_field == parent_field,
            )
            .order_by(t.c.idx)
        )
        return [row[0] for row in result.fetchall()]

    async def get_all_for_doc(
        self,
        parent_doctype: str,
        parent_id: str,
    ) -> dict[str, list[str]]:
        """Return all MultiLink values for a document, keyed by field name."""
        t = MULTI_LINK_TABLE
        result = await self.session.execute(
            select(t.c.parent_field, t.c.link_name)
            .where(
                t.c.parent_doctype == parent_doctype,
                t.c.parent_name == parent_id,
            )
            .order_by(t.c.parent_field, t.c.idx)
        )
        out: dict[str, list[str]] = {}
        for field, name in result.fetchall():
            out.setdefault(field, []).append(name)
        return out

    async def get_for_doc_fields(
        self,
        parent_doctype: str,
        parent_id: str,
        fields: list[str],
    ) -> dict[str, list[str]]:
        """Return MultiLink values only for selected field names."""
        if not fields:
            return {}

        t = MULTI_LINK_TABLE
        result = await self.session.execute(
            select(t.c.parent_field, t.c.link_name)
            .where(
                t.c.parent_doctype == parent_doctype,
                t.c.parent_name == parent_id,
                t.c.parent_field.in_(fields),
            )
            .order_by(t.c.parent_field, t.c.idx)
        )
        out: dict[str, list[str]] = {}
        for field, name in result.fetchall():
            out.setdefault(field, []).append(name)
        return out

    async def set_values(
        self,
        parent_doctype: str,
        parent_id: str,
        parent_field: str,
        link_doctype: str,
        values: list[str],
    ) -> None:
        """Replace all links for a given field with the new list (preserving order)."""
        t = MULTI_LINK_TABLE

        # Delete existing
        await self.session.execute(
            delete(t).where(
                t.c.parent_doctype == parent_doctype,
                t.c.parent_name == parent_id,
                t.c.parent_field == parent_field,
            )
        )

        # Insert new
        if values:
            rows = [
                {
                    "parent_doctype": parent_doctype,
                    "parent_name": parent_id,
                    "parent_field": parent_field,
                    "link_doctype": link_doctype,
                    "link_name": name,
                    "idx": idx,
                }
                for idx, name in enumerate(values)
            ]
            await self.session.execute(t.insert(), rows)

    async def delete_all_for_doc(
        self,
        parent_doctype: str,
        parent_id: str,
    ) -> None:
        """Remove all MultiLink entries for a document (used on document delete)."""
        t = MULTI_LINK_TABLE
        await self.session.execute(
            delete(t).where(
                t.c.parent_doctype == parent_doctype,
                t.c.parent_name == parent_id,
            )
        )

    async def delete_all_for_docs(
        self,
        parent_doctype: str,
        parent_ids: list[str],
        chunk_size: int = 500,
    ) -> None:
        """Remove all MultiLink entries for multiple documents, chunked to avoid large IN lists."""
        if not parent_ids:
            return
        t = MULTI_LINK_TABLE
        it = iter(parent_ids)
        while chunk := list(islice(it, chunk_size)):
            await self.session.execute(
                delete(t).where(
                    t.c.parent_doctype == parent_doctype,
                    t.c.parent_name.in_(chunk),
                )
            )
