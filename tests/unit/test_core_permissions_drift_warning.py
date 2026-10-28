"""Regression/feature: _inject_core() must never overwrite a core DocType's
stored `permissions` that Studio customised (they must survive framework
upgrades) — but a permissions change committed to the JSON source used to sit
inert on every live site until someone ran `grunt doctype sync` (see ADR 006:
60 of 66 core doctypes had drifted this way, unnoticed, on the project's own
dev site).

`permissions_base` remembers what the JSON said when the stored value was last
taken from it: stored permissions still equal to it were never customised and
now follow the JSON on their own. Customised ones — or ones of unknown origin,
stored before `permissions_base` existed — stay untouched with a loud warning.
"""

import pytest

DRIFT = "registry.core_permissions_drifted"


@pytest.fixture
def warnings(monkeypatch):
    from grunt import log

    caught: list[dict] = []
    monkeypatch.setattr(log, "warning", lambda event, **kw: caught.append({"event": event, **kw}))
    return caught


async def _seed(db_session, engine, name, permissions, base):
    from grunt.metadata.doctype import DocType
    from grunt.metadata.registry import doctype_registry

    stored = DocType(
        name=name,
        label=name,
        module="test",
        fields=[],
        permissions=permissions,
        permissions_base=base,
    )
    await doctype_registry.register(stored, db_session, engine)
    if base is None:
        # Stored before `permissions_base` existed - register() would record one.
        from grunt.metadata import store

        stored.permissions_base = None
        await store.update_doctype(db_session, stored)
    await db_session.commit()


async def _inject(db_session, name, permissions):
    """Inject the "current JSON source" of a core doctype; returns the active doctype."""
    from grunt.metadata import store
    from grunt.metadata.doctype import DocType
    from grunt.metadata.registry import doctype_registry

    source = DocType(name=name, label=name, module="test", fields=[], permissions=permissions)
    await doctype_registry._inject_core(source, db_session, sync_db=True)
    persisted = DocType.model_validate(await store.get_definition(db_session, name))
    return doctype_registry._doctypes[name], persisted


def _roles(perms):
    return None if perms is None else [p.role for p in perms]


@pytest.mark.asyncio
async def test_untouched_permissions_follow_the_json(ctx, db_session, engine, warnings):
    from grunt.metadata.permission import DocPermission

    seeded = [DocPermission(role="System Manager", read=True)]
    await _seed(db_session, engine, "FollowTarget", seeded, base=seeded)

    active, persisted = await _inject(
        db_session, "FollowTarget", [DocPermission(role="Manager", read=True, write=True)]
    )

    assert not [w for w in warnings if w["event"] == DRIFT]
    for dt in (active, persisted):
        assert _roles(dt.permissions) == ["Manager"]
        assert _roles(dt.permissions_base) == ["Manager"]


@pytest.mark.asyncio
async def test_customised_permissions_warn_but_are_kept(ctx, db_session, engine, warnings):
    from grunt.metadata.permission import DocPermission

    await _seed(
        db_session,
        engine,
        "CustomTarget",
        [DocPermission(role="Studio Role", read=True)],
        base=[DocPermission(role="System Manager", read=True)],
    )

    active, persisted = await _inject(
        db_session, "CustomTarget", [DocPermission(role="Manager", read=True)]
    )

    drift = [w for w in warnings if w["event"] == DRIFT]
    assert len(drift) == 1 and drift[0]["name"] == "CustomTarget"
    assert _roles(active.permissions) == ["Studio Role"]
    assert _roles(persisted.permissions) == ["Studio Role"]


@pytest.mark.asyncio
async def test_unknown_baseline_warns_but_is_kept(ctx, db_session, engine, warnings):
    from grunt.metadata.permission import DocPermission

    await _seed(
        db_session, engine, "DriftTarget", [DocPermission(role="System Manager", read=True)], None
    )

    active, _ = await _inject(
        db_session, "DriftTarget", [DocPermission(role="Manager", read=True, write=True)]
    )

    drift = [w for w in warnings if w["event"] == DRIFT]
    assert len(drift) == 1 and drift[0]["name"] == "DriftTarget"
    assert _roles(active.permissions) == ["System Manager"]


@pytest.mark.asyncio
async def test_matching_permissions_are_silent_and_record_baseline(
    ctx, db_session, engine, warnings
):
    from grunt.metadata.permission import DocPermission

    same = [DocPermission(role="System Manager", read=True)]
    await _seed(db_session, engine, "NoDriftTarget", same, None)

    _, persisted = await _inject(db_session, "NoDriftTarget", same)

    assert not [w for w in warnings if w["event"] == DRIFT]
    assert _roles(persisted.permissions_base) == ["System Manager"]


@pytest.mark.asyncio
async def test_studio_update_keeps_baseline(ctx, db_session, engine):
    from grunt.metadata.doctype import DocType
    from grunt.metadata.permission import DocPermission
    from grunt.metadata.registry import doctype_registry

    base = [DocPermission(role="System Manager", read=True)]
    await _seed(db_session, engine, "StudioTarget", base, base)

    # Studio sends the doctype back without `permissions_base`.
    edited = DocType(
        name="StudioTarget",
        label="StudioTarget",
        module="test",
        fields=[],
        permissions=[DocPermission(role="Studio Role", read=True)],
    )
    await doctype_registry.update(edited, db_session, engine)

    assert _roles(doctype_registry._doctypes["StudioTarget"].permissions_base) == [
        "System Manager"
    ]
