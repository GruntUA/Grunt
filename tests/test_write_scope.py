"""New values are checked too (PERMISSIONS_PLAN, invariant 6): a document as it
is about to be stored must satisfy the ``match`` of the rule granting
``create`` / ``write`` - a user can't create a record outside their scope, nor
carry one out of it by save or ``set_value``.

Roles: ``TeamA`` reads, writes and creates cards of team A only; ``Owner``
writes the cards they are responsible for; ``Lead`` has no row filter.
"""

import pytest
from fastapi import HTTPException

from tests.support import make_user

CARD = {
    "name": "ScopeCard",
    "label": "Scope Card",
    "module": "test",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
        {"fieldname": "team", "label": "Team", "fieldtype": "Data"},
        {"fieldname": "responsible", "label": "Responsible", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "TeamA", "actions": ["read", "write", "create"], "match": "team == 'A'"},
        {"role": "Owner", "actions": ["read", "write"], "match": "responsible == user"},
        {"role": "Lead", "actions": ["read", "write", "create"]},
    ],
}

TEAM_A = make_user("a@x.com", roles=["TeamA"])
OWNER = make_user("own@x.com", roles=["Owner"])
LEAD = make_user("lead@x.com", roles=["Lead"])


@pytest.fixture
async def card(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**CARD, "__is_new": True})
    data = {"title": "One", "team": "A", "responsible": "own@x.com"}
    name = (await ctx.new_doc("ScopeCard", data))["name"]
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
async def test_create_outside_the_scope_is_refused(card, db_session, engine):
    await _refused(
        TEAM_A, lambda g: g.new_doc("ScopeCard", {"title": "B", "team": "B"}), db_session, engine
    )
    created = await _as(
        TEAM_A, lambda g: g.new_doc("ScopeCard", {"title": "A2", "team": "A"}), db_session, engine
    )
    assert created["team"] == "A"


@pytest.mark.asyncio
async def test_save_can_not_carry_a_document_out(card, db_session, engine):
    await _refused(
        TEAM_A, lambda g: g.save_doc("ScopeCard", card, {"team": "B"}), db_session, engine
    )
    saved = await _as(
        TEAM_A, lambda g: g.save_doc("ScopeCard", card, {"title": "Two"}), db_session, engine
    )
    assert (saved["title"], saved["team"]) == ("Two", "A")


@pytest.mark.asyncio
async def test_set_value_can_not_carry_a_document_out(card, db_session, engine):
    await _refused(
        TEAM_A, lambda g: g.set_value("ScopeCard", card, "team", "B"), db_session, engine
    )
    await _refused(
        OWNER,
        lambda g: g.set_value("ScopeCard", card, {"responsible": "else@x.com"}),
        db_session,
        engine,
    )
    await _as(OWNER, lambda g: g.set_value("ScopeCard", card, "title", "Mine"), db_session, engine)
    doc = await _as(LEAD, lambda g: g.get_doc("ScopeCard", card), db_session, engine)
    assert (doc["title"], doc["team"], doc["responsible"]) == ("Mine", "A", "own@x.com")


@pytest.mark.asyncio
async def test_an_unrestricted_rule_moves_it(card, db_session, engine):
    await _as(LEAD, lambda g: g.save_doc("ScopeCard", card, {"team": "B"}), db_session, engine)
    await _as(LEAD, lambda g: g.set_value("ScopeCard", card, "team", "C"), db_session, engine)
    created = await _as(
        LEAD, lambda g: g.new_doc("ScopeCard", {"title": "X", "team": "X"}), db_session, engine
    )
    assert created["team"] == "X"
