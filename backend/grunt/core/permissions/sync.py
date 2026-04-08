"""DocTypePermission ↔ registry sync.

At startup: load all DocTypePermission rows from DB and apply them to the
in-memory DocType registry (overriding permissions stored in DocType JSON).

On after_save / after_delete of DocTypePermission: refresh in-memory perms
for that specific DocType so changes are effective immediately without restart.
"""

from __future__ import annotations

from datetime import UTC

import structlog

logger = structlog.get_logger()


async def load_all_permissions_from_db(session) -> None:  # noqa: ANN001
    """Read DocTypePermission table and inject into registry. Called at startup."""
    try:
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = doctype_registry._doctypes.get("DocTypePermission")
        if dt is None:
            return
        table = compile_doctype_to_table(dt)
        result = await session.execute(select(table))
        rows = result.fetchall()
        if not rows:
            return

        # Group by doctype_name
        by_dt: dict[str, list[dict]] = {}
        for row in rows:
            r = dict(row._mapping)
            dn = r.get("doctype_name") or ""
            if dn:
                by_dt.setdefault(dn, []).append(r)

        for doctype_name, perms in by_dt.items():
            await _apply_perms_to_doctype(doctype_name, perms)

        logger.info("permissions.loaded_from_db", count=len(rows))
    except Exception as exc:  # noqa: BLE001
        logger.warning("permissions.load_failed", error=str(exc))


async def sync_permissions(doc: dict, session=None, **_kwargs) -> None:  # noqa: ANN001
    """Hook: after_save / after_delete of DocTypePermission — refresh in-memory perms."""
    doctype_name = doc.get("doctype_name") or ""
    if not doctype_name:
        return
    if session is not None:
        await _reload_doctype_perms(doctype_name, session)


async def _reload_doctype_perms(doctype_name: str, session) -> None:  # noqa: ANN001
    try:
        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = doctype_registry._doctypes.get("DocTypePermission")
        if dt is None:
            return
        table = compile_doctype_to_table(dt)
        result = await session.execute(select(table).where(table.c.doctype_name == doctype_name))
        rows = [dict(r._mapping) for r in result.fetchall()]
        await _apply_perms_to_doctype(doctype_name, rows)
        logger.info("permissions.refreshed", doctype=doctype_name, count=len(rows))
    except Exception as exc:  # noqa: BLE001
        logger.warning("permissions.refresh_failed", doctype=doctype_name, error=str(exc))


async def _apply_perms_to_doctype(doctype_name: str, perm_rows: list[dict]) -> None:
    from grunt.core.metadata.doctype import DocTypePermission  # noqa: PLC0415
    from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

    target = doctype_registry._doctypes.get(doctype_name)
    if target is None:
        return

    perms = []
    for r in perm_rows:
        hf_raw = r.get("hidden_fields") or ""
        hidden = [f.strip() for f in hf_raw.split(",") if f.strip()] if hf_raw else []
        perms.append(
            DocTypePermission(
                role=r.get("role", ""),
                read=bool(r.get("read", False)),
                write=bool(r.get("write", False)),
                create=bool(r.get("create", False)),
                delete=bool(r.get("delete", False)),
                submit=bool(r.get("submit", False)),
                cancel=bool(r.get("cancel", False)),
                report=bool(r.get("report", False)),
                match=r.get("match") or None,
                hidden_fields=hidden,
            )
        )

    # DocTypePermission records replace (not augment) in-memory permissions
    target.permissions = perms


async def migrate_doctype_meta_permissions(session) -> None:  # noqa: ANN001
    """One-time migration: copy permissions from DocType meta JSON into DocTypePermission table.

    Only runs when the DocTypePermission table is empty.
    """
    try:
        import uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
        from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

        dt = doctype_registry._doctypes.get("DocTypePermission")
        if dt is None:
            return
        table = compile_doctype_to_table(dt)

        count_res = await session.execute(select(table.c.id).limit(1))
        if count_res.first():
            return  # Already migrated

        all_dts = await doctype_registry.list_all()
        now = datetime.now(UTC)
        inserted = 0

        for target_dt in all_dts:
            if not target_dt.permissions:
                continue
            for perm in target_dt.permissions:
                # perm may be a DocTypePermission Pydantic model or a plain dict
                if isinstance(perm, dict):
                    role = perm.get("role", "")
                    _b = lambda attr: bool(perm.get(attr, False))  # noqa: E731
                    hf_raw = perm.get("hidden_fields", [])
                    match_val = perm.get("match")
                else:
                    role = getattr(perm, "role", "")
                    _b = lambda attr: bool(getattr(perm, attr, False))  # noqa: E731
                    hf_raw = getattr(perm, "hidden_fields", [])
                    match_val = getattr(perm, "match", None)

                if not role:
                    continue

                hf_str = ", ".join(hf_raw) if isinstance(hf_raw, list) else str(hf_raw or "")

                row_id = str(uuid.uuid4())
                await session.execute(
                    table.insert().values(
                        id=row_id,
                        name=row_id[:8],
                        owner="system",
                        created_at=now,
                        modified_at=now,
                        modified_by="system",
                        docstatus=0,
                        doctype_name=target_dt.name,
                        role=role,
                        read=_b("read"),
                        write=_b("write"),
                        create=_b("create"),
                        delete=_b("delete"),
                        submit=_b("submit"),
                        cancel=_b("cancel"),
                        report=_b("report"),
                        match=match_val,
                        hidden_fields=hf_str,
                    )
                )
                inserted += 1

        if inserted:
            logger.info("permissions.migrated_from_meta", count=inserted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("permissions.migration_failed", error=str(exc))
