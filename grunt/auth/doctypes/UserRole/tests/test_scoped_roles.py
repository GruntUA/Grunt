"""Scoped roles (PERMISSIONS_PLAN step 4a): a ``UserRole`` row limited to a
scope narrows the rules of that role only - lists and single documents alike,
the new values of a write too - and an assignment out of its period gives no
role at all."""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

import grunt
from grunt.api.v1.meta import save_doctype
from grunt.local import active_role_rows, session_roles
from grunt.permissions.roles import role_holders, role_scopes
from grunt.permissions.scopes import holders_for
from tests.support import make_user

UNIT = {
    "name": "SRTestUnit",
    "label": "SR Test Unit",
    "module": "core",
    "is_tree": True,
    "tree_parent_field": "parent_unit",
    "autoname": "field:title",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {
            "fieldname": "parent_unit",
            "label": "Parent",
            "fieldtype": "Link",
            "options": "SRTestUnit",
        },
    ],
    "permissions": [{"role": "Clerk", "actions": ["read"]}],
}

LETTER = {
    "name": "SRTestLetter",
    "label": "SR Test Letter",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "unit", "label": "Unit", "fieldtype": "Link", "options": "SRTestUnit"},
        {"fieldname": "copy_to", "label": "Copy to", "fieldtype": "Link", "options": "SRTestUnit"},
        {"fieldname": "author", "label": "Author", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "Clerk", "actions": ["read", "write", "create"]},
        {"role": "Reader", "actions": ["read"], "match": "author == user"},
    ],
}

NOTE = {  # no Link to the scope: a scoped role isn't narrowed here
    "name": "SRTestNote",
    "label": "SR Test Note",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [{"role": "Clerk", "actions": ["read"]}],
}


def _scoped(role: str, unit: str, **extra: str) -> dict:
    return {"role_name": role, "scope_doctype": "SRTestUnit", "scope_value": unit, **extra}


@pytest.fixture
async def units(ctx):
    for data in (UNIT, LETTER, NOTE):
        await save_doctype(doctype_data={**data, "__is_new": True})
    for role in ("Clerk", "Reader"):
        if not await ctx.db.exists("Role", role):
            await ctx.new_doc("Role", {"role_name": role})
    await ctx.new_doc("SRTestUnit", {"title": "HQ"})
    await ctx.new_doc("SRTestUnit", {"title": "HQ-IT", "parent_unit": "HQ"})
    await ctx.new_doc("SRTestUnit", {"title": "Branch"})
    letters = {}
    for title, unit, copy_to in (
        ("hq", "HQ", None),
        ("it", "HQ-IT", None),
        ("branch", "Branch", None),
        ("none", None, None),
        ("hq-copy-branch", "HQ", "Branch"),
        ("copy-only-it", None, "HQ-IT"),
    ):
        doc = await ctx.new_doc(
            "SRTestLetter", {"title": title, "unit": unit, "copy_to": copy_to, "author": "x@e.com"}
        )
        letters[title] = doc["name"]
    await ctx.new_doc("SRTestNote", {"title": "note"})
    await ctx.db._session().commit()
    return letters


async def _titles(doctype: str = "SRTestLetter") -> set[str]:
    return {r["title"] for r in await grunt.get_list(doctype, fields=["title"])}


@pytest.mark.asyncio
async def test_scope_narrows_list_and_document_with_subtree(ctx, units, db_session, engine):
    clerk = make_user("clerk@example.com", roles=[_scoped("Clerk", "HQ")])
    async with grunt.context(db_session, engine, clerk):
        # HQ and its subtree; a letter with no unit lies outside every scope;
        # with two Links every filled one must be in scope.
        assert await _titles() == {"hq", "it", "copy-only-it"}
        assert (await grunt.get_doc("SRTestLetter", units["it"])).title == "it"
        with pytest.raises(HTTPException) as exc:
            await grunt.get_doc("SRTestLetter", units["branch"])
        assert exc.value.status_code == 403
        # The scope DocType itself is narrowed by ``name``.
        assert await _titles("SRTestUnit") == {"HQ", "HQ-IT"}
        # A DocType that doesn't link to the scope isn't narrowed.
        assert await _titles("SRTestNote") == {"note"}


@pytest.mark.asyncio
async def test_scopes_of_one_role_widen_each_other(ctx, units, db_session, engine):
    clerk = make_user(
        "clerk@example.com", roles=[_scoped("Clerk", "HQ-IT"), _scoped("Clerk", "Branch")]
    )
    async with grunt.context(db_session, engine, clerk):
        assert await _titles() == {"it", "branch", "copy-only-it"}


@pytest.mark.asyncio
async def test_unscoped_assignment_holds_everywhere(ctx, units, db_session, engine):
    clerk = make_user("clerk@example.com", roles=[_scoped("Clerk", "HQ"), "Clerk"])
    async with grunt.context(db_session, engine, clerk):
        assert len(await _titles()) == len(units)


@pytest.mark.asyncio
async def test_scope_narrows_its_own_role_only(ctx, units, db_session, engine):
    """The Reader rule (own letters) isn't cut by the Clerk scope - unlike a
    User Permission, which narrowed every role."""
    user = make_user("x@e.com", roles=[_scoped("Clerk", "Branch"), "Reader"])
    async with grunt.context(db_session, engine, user):
        assert len(await _titles()) == len(units)
    user = make_user("y@e.com", roles=[_scoped("Clerk", "Branch"), "Reader"])
    async with grunt.context(db_session, engine, user):
        assert await _titles() == {"branch"}


@pytest.mark.asyncio
async def test_new_values_stay_in_scope(ctx, units, db_session, engine):
    clerk = make_user("clerk@example.com", roles=[_scoped("Clerk", "HQ")])
    async with grunt.context(db_session, engine, clerk):
        with pytest.raises(HTTPException) as exc:
            await grunt.new_doc("SRTestLetter", {"title": "out", "unit": "Branch"})
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await grunt.save_doc("SRTestLetter", units["hq"], {"unit": "Branch"})
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException):
            await grunt.new_doc("SRTestLetter", {"title": "nowhere"})
        created = await grunt.new_doc("SRTestLetter", {"title": "in", "unit": "HQ-IT"})
        assert created.unit == "HQ-IT"


@pytest.mark.asyncio
async def test_assignment_out_of_period_gives_no_role(ctx, units, db_session, engine):
    today = date.today()
    expired = {"role_name": "Clerk", "valid_to": (today - timedelta(days=1)).isoformat()}
    future = {"role_name": "Clerk", "valid_from": (today + timedelta(days=1)).isoformat()}
    current = {"role_name": "Clerk", "valid_from": today.isoformat(), "valid_to": today.isoformat()}
    assert active_role_rows([expired, future]) == []
    assert active_role_rows([current]) == [current]
    async with grunt.context(db_session, engine, make_user("c@e.com", roles=[expired])):
        assert session_roles() == []
        with pytest.raises(HTTPException):
            await grunt.get_list("SRTestLetter")


def test_role_scopes():
    rows = [_scoped("Clerk", "HQ"), _scoped("Clerk", "Branch"), _scoped("Boss", "HQ"), "Boss"]
    assert role_scopes(active_role_rows(rows)) == {
        "Clerk": frozenset({("SRTestUnit", "HQ"), ("SRTestUnit", "Branch")})
    }


@pytest.mark.asyncio
async def test_role_holders_and_holders_for_a_document(ctx, units):
    today = date.today()
    await ctx.new_doc(
        "User",
        {
            "email": "hq@example.com",
            "first_name": "H",
            "last_name": "Q",
            "roles": [_scoped("Clerk", "HQ")],
        },
    )
    await ctx.new_doc(
        "User",
        {
            "email": "all@example.com",
            "first_name": "A",
            "last_name": "L",
            "roles": [{"role_name": "Clerk"}],
        },
    )
    await ctx.new_doc(
        "User",
        {
            "email": "old@example.com",
            "first_name": "O",
            "last_name": "L",
            "roles": [{"role_name": "Clerk", "valid_to": (today - timedelta(days=3)).isoformat()}],
        },
    )
    await ctx.db._session().commit()

    emails = {h["email"] for h in await role_holders(["Clerk"])}
    assert {"hq@example.com", "all@example.com"} <= emails
    assert "old@example.com" not in emails

    meta = await grunt.get_meta("SRTestLetter")
    branch = await ctx.db.get_doc("SRTestLetter", units["branch"])
    it = await ctx.db.get_doc("SRTestLetter", units["it"])
    for_branch = set(await holders_for(["Clerk"], meta, branch))
    for_it = set(await holders_for(["Clerk"], meta, it))
    assert "hq@example.com" not in for_branch and "all@example.com" in for_branch
    assert {"hq@example.com", "all@example.com"} <= for_it


@pytest.mark.asyncio
async def test_scope_needs_a_value_and_period_order(ctx, units):
    # Messages are translated - check the status and the role, not the wording.
    with pytest.raises(Exception, match=r"422.*Clerk"):
        await ctx.new_doc(
            "User",
            {
                "email": "bad@example.com",
                "first_name": "B",
                "last_name": "D",
                "roles": [{"role_name": "Clerk", "scope_doctype": "SRTestUnit"}],
            },
        )
    with pytest.raises(Exception, match=r"422.*Clerk"):
        await ctx.new_doc(
            "User",
            {
                "email": "bad2@example.com",
                "first_name": "B",
                "last_name": "D",
                "roles": [
                    {"role_name": "Clerk", "valid_from": "2026-02-01", "valid_to": "2026-01-01"}
                ],
            },
        )
