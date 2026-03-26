"""Client Script service — manages JavaScript scripts injected into the frontend.

Client scripts are stored in the database and served to the frontend per DocType.
The frontend executor runs them in the form context (on_load, on_change, validate, etc.).
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def get_client_scripts(
    session: AsyncSession,
    doctype: str,
) -> list[dict[str, Any]]:
    """Load all enabled client scripts for a DocType.

    Returns a list of dicts with `name` and `script` keys.
    """
    from grunt.core.db.system_tables import GruntClientScript  # noqa: PLC0415

    stmt = (
        select(GruntClientScript)
        .where(GruntClientScript.doctype == doctype)
        .where(GruntClientScript.is_enabled.is_(True))
        .order_by(GruntClientScript.name)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [{"name": r.name, "script": r.script} for r in rows]
