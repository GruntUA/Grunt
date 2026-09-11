"""Regression/feature: _inject_core() deliberately never overwrites a core
DocType's stored `permissions` once seeded (Studio customisations must
survive framework upgrades) — but that silence meant a permissions change
committed to the JSON source could sit inert on a live site indefinitely,
discovered only by accident (see ADR 006: 60 of 66 core doctypes had drifted
this way, unnoticed, on the project's own dev site). _inject_core() must now
log a loud warning whenever the JSON and stored permissions disagree, while
still leaving the stored (Studio-owned) value untouched.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_inject_core_warns_on_permissions_drift_but_does_not_overwrite(
    ctx, db_session, engine, monkeypatch
):
    from grunt.log import log
    from grunt.metadata.doctype import DocType
    from grunt.metadata.permission import DocPermission
    from grunt.metadata.registry import doctype_registry

    # Seed a "core" doctype the way _inject_core's first-run branch would,
    # with an initial permissions set (stands in for "already installed").
    stored = DocType(
        name="DriftTarget",
        label="Drift Target",
        module="test",
        fields=[],
        permissions=[DocPermission(role="System Manager", read=True)],
    )
    await doctype_registry.register(stored, db_session, engine)
    await db_session.commit()

    warnings: list[dict] = []
    monkeypatch.setattr(
        log,
        "warning",
        lambda event, **kw: warnings.append({"event": event, **kw}),
    )

    # The "current JSON source" now grants a different role — simulates a
    # permissions edit committed to disk after the site was first installed.
    updated_json = DocType(
        name="DriftTarget",
        label="Drift Target",
        module="test",
        fields=[],
        permissions=[DocPermission(role="Manager", read=True, write=True)],
    )
    await doctype_registry._inject_core(updated_json, db_session, sync_db=True)

    drift_warnings = [w for w in warnings if w["event"] == "registry.core_permissions_drifted"]
    assert len(drift_warnings) == 1
    assert drift_warnings[0]["name"] == "DriftTarget"

    # Stored (Studio-owned) permissions must survive untouched — only the
    # warning changed, not the seed-once behaviour.
    active = doctype_registry._doctypes["DriftTarget"]
    assert [p.role for p in active.permissions] == ["System Manager"]


@pytest.mark.asyncio
async def test_inject_core_silent_when_permissions_match(ctx, db_session, engine, monkeypatch):
    from grunt.log import log
    from grunt.metadata.doctype import DocType
    from grunt.metadata.permission import DocPermission
    from grunt.metadata.registry import doctype_registry

    same_perms = [DocPermission(role="System Manager", read=True)]
    stored = DocType(
        name="NoDriftTarget", label="No Drift", module="test", fields=[], permissions=same_perms
    )
    await doctype_registry.register(stored, db_session, engine)
    await db_session.commit()

    warnings: list[dict] = []
    monkeypatch.setattr(
        log,
        "warning",
        lambda event, **kw: warnings.append({"event": event, **kw}),
    )

    same_json = DocType(
        name="NoDriftTarget", label="No Drift", module="test", fields=[], permissions=same_perms
    )
    await doctype_registry._inject_core(same_json, db_session, sync_db=True)

    assert not [w for w in warnings if w["event"] == "registry.core_permissions_drifted"]
