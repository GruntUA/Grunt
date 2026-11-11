"""A field read-only for a role (``DocPermission.readonly_fields``): the user
sees it, a new document takes its value, but an existing one keeps it - through
save, ``set_value`` and the form (``__perms``).

Roles: ``Accountant`` reads and writes a card but ``salary`` is read-only;
``HR`` changes everything. ``Both`` holds both roles - the widest rule wins.
"""

import pytest
from fastapi import HTTPException

from grunt.permissions.doc_perms import doc_permissions
from tests.support import make_user

CARD = {
    "name": "RoCard",
    "label": "Ro Card",
    "module": "test",
    "fields": [
        {"fieldname": "full_name", "label": "Full name", "fieldtype": "Data"},
        {"fieldname": "salary", "label": "Salary", "fieldtype": "Int"},
    ],
    "permissions": [
        {
            "role": "Accountant",
            "actions": ["read", "write", "create"],
            "readonly_fields": ["salary"],
        },
        {"role": "HR", "actions": ["read", "write", "create"]},
    ],
}

ACCOUNTANT = make_user("acc@x.com", roles=["Accountant"])
HR = make_user("hr@x.com", roles=["HR"])
BOTH = make_user("both@x.com", roles=["Accountant", "HR"])


@pytest.fixture
async def card(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**CARD, "__is_new": True})
    name = (await ctx.new_doc("RoCard", {"full_name": "Ann", "salary": 100}))["name"]
    await ctx.db._session().commit()
    return name


async def _as(user, call, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, user):
        return await call(grunt)


async def _refused(user, call, db_session, engine):
    with pytest.raises(HTTPException) as exc_info:
        await _as(user, call, db_session, engine)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_read_only_field_is_visible_but_kept(card, db_session, engine):
    doc = await _as(ACCOUNTANT, lambda g: g.get_doc("RoCard", card), db_session, engine)
    assert doc["salary"] == 100

    await _refused(
        ACCOUNTANT,
        lambda g: g.save_doc("RoCard", card, {**doc, "salary": 999}),
        db_session,
        engine,
    )
    await _refused(
        ACCOUNTANT, lambda g: g.set_value("RoCard", card, "salary", 999), db_session, engine
    )
    # The rest of the document stays editable; sending the same value back is fine.
    saved = await _as(
        ACCOUNTANT,
        lambda g: g.save_doc("RoCard", card, {**doc, "full_name": "Anna"}),
        db_session,
        engine,
    )
    assert (saved["full_name"], saved["salary"]) == ("Anna", 100)


@pytest.mark.asyncio
async def test_new_document_takes_the_value(card, db_session, engine):
    created = await _as(
        ACCOUNTANT,
        lambda g: g.new_doc("RoCard", {"full_name": "Bob", "salary": 50}),
        db_session,
        engine,
    )
    assert created["salary"] == 50


@pytest.mark.asyncio
async def test_a_role_that_may_change_it_wins(card, db_session, engine):
    for user in (HR, BOTH):
        await _as(user, lambda g: g.set_value("RoCard", card, "salary", 200), db_session, engine)


@pytest.mark.asyncio
async def test_form_gets_read_only_fields(card, db_session, engine):
    async def perms(g):
        return await doc_permissions("RoCard", await g.get_doc("RoCard", card))

    assert (await _as(ACCOUNTANT, perms, db_session, engine))["readonly_fields"] == ["salary"]
    assert (await _as(HR, perms, db_session, engine))["readonly_fields"] == []


@pytest.mark.asyncio
async def test_unknown_field_is_refused_on_save(ctx):
    from grunt.api.v1.meta import save_doctype

    broken = {
        **CARD,
        "name": "RoTypo",
        "label": "Ro Typo",
        "permissions": [{"role": "HR", "actions": ["read", "write"], "readonly_fields": ["salry"]}],
    }
    with pytest.raises(HTTPException) as exc_info:
        await save_doctype(doctype_data={**broken, "__is_new": True})
    assert exc_info.value.status_code == 422
    assert "salry" in exc_info.value.detail


def test_studio_text_is_a_list():
    from grunt.metadata.permission import DocPermission

    row = DocPermission(role="HR", hidden_fields="a, b", readonly_fields="c\nd")
    assert (row.hidden_fields, row.readonly_fields) == (["a", "b"], ["c", "d"])
