"""Client Script service — manages JavaScript scripts injected into the frontend.

Client scripts are stored in the database and served to the frontend per DocType.
The frontend executor runs them in the form context (on_load, on_change, validate, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.log import log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_client_scripts(
    session: AsyncSession,
    doctype: str,
) -> list[dict[str, Any]]:
    """Load all enabled client scripts for a DocType.

    Returns a list of dicts with `name` and `script` keys.
    """
    from grunt.app import GruntDB
    from grunt.local import _session_ctx

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
    log.info("client_scripts.db_scripts", doctype=doctype, count=len(scripts))

    # Append file-based client scripts (from app directories)
    try:
        from grunt.scripting.file_scripts import get_file_client_scripts

        file_scripts = get_file_client_scripts(doctype)
        log.info(
            "client_scripts.file_scripts",
            doctype=doctype,
            count=len(file_scripts),
            names=[s["name"] for s in file_scripts],
        )
        scripts.extend(file_scripts)
    except ImportError:
        log.debug(
            "Optional file-based client scripts module not available; "
            "continuing with database-backed scripts only.",
            doctype=doctype,
        )

    log.info("client_scripts.total", doctype=doctype, total=len(scripts))
    return scripts
