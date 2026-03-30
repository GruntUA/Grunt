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
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415
    from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415

    table = compile_doctype_to_table(doctype_registry._doctypes["ClientScript"])
    stmt = (
        select(table)
        .where(table.c.doctype == doctype)
        .where(table.c.is_enabled.is_(True))
        .order_by(table.c.name)
    )
    result = await session.execute(stmt)
    rows = result.mappings().all()
    scripts: list[dict[str, Any]] = [{"name": r["name"], "script": r["script"]} for r in rows]

    # Append file-based client scripts (from app directories)
    try:
        from grunt.core.scripting.file_scripts import get_file_client_scripts  # noqa: PLC0415

        scripts.extend(get_file_client_scripts(doctype))
    except ImportError:
        logger.debug(
            "Optional file-based client scripts module not available; "
            "continuing with database-backed scripts only.",
            doctype=doctype,
        )

    return scripts
