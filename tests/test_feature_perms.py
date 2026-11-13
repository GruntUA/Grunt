"""Who may run a document action or take a workflow step (PERMISSIONS_PLAN 3b):
an action declares the rule action it needs on the document (``requires``), a
permission (``perm``) or - the older form - roles; nobody gets in by the role
*name* "System Manager", only by holding every permission (``*``).
"""

import pytest
from fastapi import HTTPException

from grunt.actions import run
from grunt.actions.registry import _REGISTRY, doc_action
from grunt.errors import APIError
from tests.support import make_user

BOX = {
    "name": "FpBox",
    "label": "Fp Box",
    "module": "test",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete"]},
        {"role": "Reader", "actions": ["read"]},
        {"role": "Writer", "actions": ["read", "write"]},
        {"role": "Mailer", "actions": ["read"]},
        {"role": "Locked", "actions": ["read", "write"], "readonly_fields": ["title"]},
    ],
    "actions": [
        {"action": "fp.write"},
        {"action": "fp.mail"},
        {"action": "fp.roles"},
        {"action": "core.reset_standard"},
    ],
}

READER = make_user("reader@x.com", roles=["Reader"])
WRITER = make_user("writer@x.com", roles=["Writer"])
MAILER = make_user("mailer@x.com", roles=["Mailer"])
ADMIN = make_user("admin@x.com", roles=["System Manager"])
LOCKED = make_user("locked@x.com", roles=["Locked"])


@pytest.fixture
async def box(ctx):
    from grunt.api.v1.meta import save_doctype

    async def ok(doc, *, args):
        return "ok"

    doc_action("fp.write", label="W", doctypes=["FpBox"], requires="write")(ok)
    doc_action("fp.mail", label="M", doctypes=["FpBox"], perm="grunt.manage_email")(ok)
    doc_action("fp.roles", label="R", doctypes=["FpBox"], roles=["Writer"])(ok)
    await ctx.new_doc("Role", {"role_name": "Mailer", "permissions": ["grunt.manage_email"]})
    await save_doctype(doctype_data={**BOX, "__is_new": True})
    name = (await ctx.new_doc("FpBox", {"title": "One"}))["name"]
    await ctx.db._session().commit()
    yield name
    for key in ("fp.write", "fp.mail", "fp.roles"):
        _REGISTRY.pop(key, None)


async def _run(user, action, name, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, user):
        return await run("FpBox", action, name)


async def _refused(user, action, name, db_session, engine):
    with pytest.raises((HTTPException, APIError)) as exc_info:
        await _run(user, action, name, db_session, engine)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_requires_a_rule_action_on_the_document(box, db_session, engine):
    await _refused(READER, "fp.write", box, db_session, engine)
    assert (await _run(WRITER, "fp.write", box, db_session, engine))["message"] == "ok"


@pytest.mark.asyncio
async def test_perm(box, db_session, engine):
    await _refused(READER, "fp.mail", box, db_session, engine)
    assert (await _run(MAILER, "fp.mail", box, db_session, engine))["message"] == "ok"
    assert (await _run(ADMIN, "fp.mail", box, db_session, engine))["message"] == "ok"


@pytest.mark.asyncio
async def test_roles_and_everything(box, db_session, engine):
    await _refused(READER, "fp.roles", box, db_session, engine)
    assert (await _run(WRITER, "fp.roles", box, db_session, engine))["message"] == "ok"
    # Not by the role name - by "*", which System Manager holds.
    assert (await _run(ADMIN, "fp.roles", box, db_session, engine))["message"] == "ok"


def test_transition_roles():
    from grunt.metadata.doctype import WorkflowTransition
    from grunt.workflow.transition import user_may_take

    t = WorkflowTransition(from_state="A", to_state="B", action="Go", allowed_roles=["Approver"])
    assert user_may_take(t, ["Approver"])
    assert not user_may_take(t, ["System Manager"])  # a name grants nothing
    assert user_may_take(t, ["Clerk"], unrestricted=True)  # "*" does


@pytest.mark.asyncio
async def test_reset_to_standard_needs_no_field_locks(box, db_session, engine):
    # The reset writes every field as the system - not for a writer with locked fields.
    await _refused(LOCKED, "core.reset_standard", box, db_session, engine)
    result = await _run(WRITER, "core.reset_standard", box, db_session, engine)
    assert result["message"]  # past the check: the app ships no such record
