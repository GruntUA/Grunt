"""Client Script service — manages JavaScript scripts injected into the frontend.

Client scripts are stored in the database and served to the frontend per DocType.
The frontend executor runs them in the form context (on_load, on_change, validate, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def get_client_scripts(
    session: AsyncSession,
    doctype: str,
) -> list[dict[str, Any]]:
    """Load all enabled client scripts for a DocType.

    Returns a list of dicts with `name` and `script` keys.
    """
    from grunt.app import GruntDB  # noqa: PLC0415
    from grunt.core.context import _session_ctx  # noqa: PLC0415

    token = _session_ctx.set(session)
    try:
        rows = await GruntDB().get_all(
            "ClientScript",
            filters={"doctype": doctype, "is_enabled": True},
            fields=["name", "script"],
            limit=10_000,
            order_by="name",
            order="asc",
        )
    finally:
        _session_ctx.reset(token)

    scripts: list[dict[str, Any]] = [
        {"name": str(r.get("name") or ""), "script": str(r.get("script") or "")} for r in rows
    ]

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
