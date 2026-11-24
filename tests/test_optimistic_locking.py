"""Optimistic locking on update: a save based on an outdated copy of the
document is refused with 409 instead of silently overwriting the newer one.

Two layers: the ``modified_at`` the edit was based on (the form and
``doc.save()`` send the whole document; offline replays send
``__base_modified_at``), and the guarded UPDATE in ``SqlStore`` that catches a
write landing between the load and the UPDATE."""

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from grunt.auth.doctypes.Role.role import Role

DOCS = "/api/v1/docs/Role"


async def _role(client, auth_headers, name: str) -> dict:
    r = await client.post(DOCS, json={"role_name": name}, headers=auth_headers)
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


@pytest.mark.asyncio
async def test_stale_form_save_is_a_conflict(client, auth_headers):
    role = await _role(client, auth_headers, "Lock Form Clerk")
    url = f"{DOCS}/{role['name']}"

    # Someone else saves first…
    theirs = await client.put(url, json={"description": "theirs"}, headers=auth_headers)
    assert theirs.status_code == 200, theirs.text

    # …so the form still holding the old copy (whole document, old modified_at) is refused.
    stale = await client.put(url, json={**role, "description": "mine"}, headers=auth_headers)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "STALE_DOCUMENT"  # the desk offers a reload
    got = await client.get(url, headers=auth_headers)
    assert got.json()["data"]["description"] == "theirs"

    # Reloaded, the same edit goes through - and saving the result again does too.
    fresh = theirs.json()["data"]
    ok = await client.put(url, json={**fresh, "description": "mine"}, headers=auth_headers)
    assert ok.status_code == 200, ok.text
    again = await client.put(url, json=ok.json()["data"], headers=auth_headers)
    assert again.status_code == 200, again.text


@pytest.mark.asyncio
async def test_partial_update_without_stamp_is_not_checked(client, auth_headers):
    """Kanban, inline edits… send only the changed fields - nothing to compare."""
    role = await _role(client, auth_headers, "Lock Partial Clerk")
    url = f"{DOCS}/{role['name']}"
    for text_ in ("one", "two"):
        r = await client.put(url, json={"description": text_}, headers=auth_headers)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_stale_document_instance_save_is_a_conflict(ctx, db_session):
    await ctx.new_doc("Role", {"role_name": "Lock Instance Clerk"})
    mine = await Role.get_doc("Lock Instance Clerk")
    theirs = await Role.get_doc("Lock Instance Clerk")

    theirs.data["description"] = "theirs"
    await theirs.save()

    mine.data["description"] = "mine"
    with pytest.raises(HTTPException) as exc:
        await mine.save()
    assert exc.value.status_code == 409

    # The instance that saved is up to date - it saves again.
    theirs.data["description"] = "theirs again"
    await theirs.save()
    assert (await ctx.get_doc("Role", "Lock Instance Clerk"))["description"] == "theirs again"


@pytest.mark.asyncio
async def test_write_between_load_and_update_is_a_conflict(ctx, db_session):
    """The UPDATE itself is conditional: a row changed after the pipeline
    loaded it (a concurrent request) is not overwritten."""
    from grunt.metadata.registry import doctype_registry
    from grunt.store.lookup import store_for

    await ctx.new_doc("Role", {"role_name": "Lock Race Clerk"})
    meta = await doctype_registry.get_meta("Role")
    store = store_for(meta, db_session)
    loaded = await store.get("Lock Race Clerk")
    assert loaded is not None

    # A concurrent save lands after the load.
    other = await Role.get_doc("Lock Race Clerk")
    other.data["description"] = "theirs"
    await other.save()

    with pytest.raises(HTTPException) as exc:
        await store.update(
            "Lock Race Clerk",
            {**loaded, "description": "mine"},
            before=loaded,
            input={"description": "mine"},
            user="system@grunt.local",
        )
    assert exc.value.status_code == 409
    assert (await ctx.get_doc("Role", "Lock Race Clerk"))["description"] == "theirs"


@pytest.mark.asyncio
async def test_stamp_stored_in_another_format_still_saves(ctx, db_session):
    """An imported row may hold ``...T...+00:00`` (or no microseconds) - the
    same moment, another text; the SQL comparison misses, the fallback
    compares moments and the save goes through."""
    if db_session.bind.dialect.name != "sqlite":
        pytest.skip("only SQLite keeps the stamp as text")
    from grunt.metadata.registry import doctype_registry

    await ctx.new_doc("Role", {"role_name": "Lock Format Clerk"})
    table = (await doctype_registry.get_meta("Role")).table.name
    await db_session.execute(
        text(f'UPDATE "{table}" SET modified_at = :v WHERE name = :n'),
        {"v": "2026-01-02T03:04:05+00:00", "n": "Lock Format Clerk"},
    )

    doc = await Role.get_doc("Lock Format Clerk")
    doc.data["description"] = "saved"
    await doc.save()
    assert (await ctx.get_doc("Role", "Lock Format Clerk"))["description"] == "saved"


@pytest.mark.asyncio
async def test_format_fallback_retry_is_still_guarded(ctx, db_session, monkeypatch):
    """A commit landing between the fallback's read-back and its retry is
    refused too - the retry is conditional on the stamp text it read."""
    if db_session.bind.dialect.name != "sqlite":
        pytest.skip("only SQLite keeps the stamp as text")
    import grunt.store.sql as sql_store
    from grunt.document.serde import same_instant
    from grunt.metadata.registry import doctype_registry

    await ctx.new_doc("Role", {"role_name": "Lock Fallback Clerk"})
    table = (await doctype_registry.get_meta("Role")).table.name
    await db_session.execute(
        text(f'UPDATE "{table}" SET modified_at = :v WHERE name = :n'),
        {"v": "2026-01-02T03:04:05+00:00", "n": "Lock Fallback Clerk"},
    )
    doc = await Role.get_doc("Lock Fallback Clerk")

    read_back = False

    def _mark_read_back(a, b):
        nonlocal read_back
        read_back = True
        return same_instant(a, b)

    execute = db_session.execute

    async def _execute(statement, *args, **kwargs):
        nonlocal read_back
        if read_back:  # the retry is next - another session's save lands first
            read_back = False
            await execute(
                text(f'UPDATE "{table}" SET modified_at = :v, description = :d WHERE name = :n'),
                {"v": "2026-05-06 07:08:09.000000", "d": "theirs", "n": "Lock Fallback Clerk"},
            )
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(sql_store, "same_instant", _mark_read_back)
    monkeypatch.setattr(db_session, "execute", _execute)
    doc.data["description"] = "mine"
    with pytest.raises(HTTPException) as exc:
        await doc.save()
    assert exc.value.status_code == 409
