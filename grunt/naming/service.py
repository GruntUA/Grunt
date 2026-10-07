"""NamingService - generates document names from DocType autoname patterns.

Supports:
  - "field:<fieldname>"          -> use a field value as the name
  - "hash"                       -> short random token
  - "prompt"                     -> user supplies name explicitly
  - "PREFIX-.YYYY.-.####"        -> pattern with date tokens and auto-incrementing counter
  - ""  (empty)                  -> falls back to "hash"
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

import grunt
from grunt import _, log
from grunt.errors import not_found
from grunt.naming.patterns import (
    build_prefix,
    format_name,
    has_counter,
    parse_pattern,
    resolve_simple,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class NamingService:
    """Generates unique document names based on DocType autoname patterns."""

    async def generate(
        self,
        autoname: str,
        data: dict[str, Any],
        session: AsyncSession,
    ) -> str:
        """Generate a name for a new document.

        Always returns a non-empty string. When autoname is empty or unresolvable,
        falls back to the "hash" pattern (short random token).

        Args:
            autoname: The autoname pattern from the DocType definition.
            data: The document data (for field-based naming).
            session: DB session for counter operations.

        Returns:
            The generated name.
        """
        # Strip optional "format:" prefix stored by the Studio UI
        if autoname.startswith("format:"):
            autoname = autoname[7:]

        # Empty autoname -> use hash as fallback
        if not autoname:
            autoname = "hash"

        # Try simple patterns first (field:, hash, prompt)
        simple = resolve_simple(autoname, data)
        if simple is not None:
            return simple

        # Parse pattern-based autoname
        parts = parse_pattern(autoname)
        if not parts:
            # Unrecognised pattern - fall back to hash
            return resolve_simple("hash", data)  # type: ignore[return-value]

        now = datetime.now(UTC)

        if not has_counter(parts):
            # Pattern without counter - just format date tokens
            return format_name(parts, counter=0, now=now)

        # Pattern with counter - need atomic increment
        prefix = build_prefix(parts, now=now)
        counter = await self._next_counter(prefix, session)
        name = format_name(parts, counter=counter, now=now)

        log.debug("naming.generated", pattern=autoname, prefix=prefix, counter=counter, name=name)
        return name

    async def _next_counter(self, prefix: str, session: AsyncSession) -> int:
        """Atomically increment and return the next counter for a prefix.

        Uses SELECT ... FOR UPDATE to prevent race conditions.
        """
        ns_dt = await grunt.get_meta("NamingSeries")
        if ns_dt is None:
            raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "NamingSeries"})
        table = ns_dt.table

        # Try to get existing row with lock
        stmt = select(table).where(table.c.prefix == prefix).with_for_update()
        result = await session.execute(stmt)
        row = result.mappings().first()

        if row is not None:
            new_counter = (row["current"] or 0) + 1
            await session.execute(
                update(table).where(table.c.prefix == prefix).values(current=new_counter)
            )
            await session.flush()
            return new_counter

        # First time - insert with counter = 1
        now = datetime.now(UTC)
        await session.execute(
            table.insert().values(
                name=prefix,
                owner="system",
                created_at=now,
                modified_at=now,
                modified_by="system",
                prefix=prefix,
                current=1,
            )
        )
        await session.flush()
        return 1
