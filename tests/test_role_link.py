"""A permission rule names a role that exists (PERMISSIONS_PLAN 3c): saving a
DocType with a rule for an unknown role is refused - a typo would grant nothing
and say nothing. ``All`` and ``Guest`` are built-in principals, shipped as
standard Role records for the picker."""

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.permissions.roles import missing_roles

BOOK = {
    "name": "RlBook",
    "label": "Rl Book",
    "module": "test",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write"]},
        {"role": "Gone", "actions": ["read"]},  # a role deleted since
    ],
}


@pytest.fixture
async def book(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOOK, "__is_new": True})
    await ctx.new_doc("Role", {"role_name": "Clerk"})
    await ctx.db._session().commit()


async def _save(ctx, rules: list[dict]) -> None:
    await ctx.save_doc("DocType", "RlBook", {"permissions": [*BOOK["permissions"], *rules]})


@pytest.mark.asyncio
async def test_unknown_role_is_refused(book, ctx):
    with pytest.raises((HTTPException, ApplicationError)) as exc_info:
        await _save(ctx, [{"role": "Clrek", "actions": ["read"]}])
    assert getattr(exc_info.value, "status_code", None) == 422
    assert "Clrek" in str(getattr(exc_info.value, "detail", exc_info.value))


@pytest.mark.asyncio
async def test_existing_and_built_in_roles_pass(book, ctx):
    # The old rule for "Gone" stays and doesn't block the edit.
    await _save(
        ctx,
        [
            {"role": "Clerk", "actions": ["read"]},
            {"role": "All", "actions": ["read"]},
            {"role": "Guest", "actions": ["read"]},
        ],
    )
    meta = await ctx.get_meta("RlBook")
    assert [p.role for p in meta.permissions] == ["System Manager", "Gone", "Clerk", "All", "Guest"]


@pytest.mark.asyncio
async def test_missing_roles(book):
    assert await missing_roles(["Clerk", "All", "Guest", "Gone", ""]) == ["Gone"]


@pytest.mark.asyncio
async def test_built_in_roles_ship_as_records(ctx, db_session, engine):
    from grunt.standard_records import apply_records

    await apply_records("grunt", db_session, engine, doctype="Role")
    assert await ctx.db.exists("Role", "All")
    assert await ctx.db.exists("Role", "Guest")
