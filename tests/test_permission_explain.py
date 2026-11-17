"""The access inspector (PERMISSIONS_PLAN step 6a): its verdict is the
permission check itself, and the trace always names a reason for it - a rule
that let the document through, a share, or a document access follows - and
none when access is denied."""

import pytest

from tests.contract.test_permissions import (  # noqa: F401 - fixture
    NOTES,
    TASK_CASES,
    TASKS,
    permission_data,
)
from tests.support import make_user

pytestmark = pytest.mark.usefixtures("permission_data")


def _reasons(trace: dict) -> list[str]:
    found = [
        f"rule {r['index']}" for r in trace["rules"] if r["held"] and r["grants"] and r["doc_ok"]
    ]
    found += [f"share {s['name']}" for s in trace["shares"]]
    if trace["role_grants"]:  # following a document still needs a rule at all
        found += [f"via {f['doctype']} {f['name']}" for f in trace["followed"] if f["allowed"]]
    return found


@pytest.mark.asyncio
@pytest.mark.parametrize("case", TASK_CASES, ids=lambda c: c[0].split("@")[0])
async def test_trace_names_a_reason_exactly_when_allowed(ctx, db_session, engine, case):
    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.explain import explain
    from grunt.permissions.rbac import permission_checker

    email, roles, _ = case
    user = make_user(email, roles=roles)
    for doctype, names in (("CpTask", TASKS), ("CpNote", NOTES)):
        meta = await doctype_registry.get_meta(doctype)
        async with grunt.context(db_session, engine, user):
            for name in names:
                doc = await grunt.db.get_value(doctype, name, "*", as_dict=True)
                trace = await explain(email, meta, "read", doc)
                assert trace["allowed"] == await permission_checker.check(
                    meta, "read", doc, user=email
                )
                assert bool(_reasons(trace)) == trace["allowed"], (email, roles, doctype, name)


@pytest.mark.asyncio
async def test_trace_shows_rules_scopes_and_shares(ctx, db_session, engine):
    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.explain import explain

    erin = make_user(
        "erin@x.com",
        roles=[{"role_name": "Own", "scope_doctype": "CpTeam", "scope_value": "T2"}],
    )
    meta = await doctype_registry.get_meta("CpTask")
    async with grunt.context(db_session, engine, erin):
        doc = await grunt.db.get_value("CpTask", "K1", "*", as_dict=True)
        trace = await explain("erin@x.com", meta, "read", doc)
    assert trace["allowed"] is True
    own = next(r for r in trace["rules"] if r["role"] == "Own")
    assert own["held"] and own["match"] == "assignee == user"
    assert own["scopes"] == [{"doctype": "CpTeam", "values": ["T2"]}]
    assert own["doc_ok"] is False  # K1 is alice's, in T1
    assert [s["via"] for s in trace["shares"]] == ["user"]  # the share lets her in
    assert trace["roles"][0]["scope_value"] == "T2"
    # Roles she lacks are listed too - "who would get access".
    assert any(r["role"] == "Reader" and not r["held"] for r in trace["rules"])


@pytest.mark.asyncio
async def test_child_row_follows_its_parent(ctx, db_session, engine):
    import grunt
    from grunt.metadata.registry import doctype_registry
    from grunt.permissions.explain import explain

    alice = make_user("alice@x.com", roles=["Own"])
    meta = await doctype_registry.get_meta("CpStep")
    async with grunt.context(db_session, engine, alice):
        rows = await grunt.db.get_all("CpStep", fields=["*"], limit=None)
        for row in rows:
            trace = await explain("alice@x.com", meta, "read", row)
            assert trace["child"] and trace["rules"] == []
            assert [f["allowed"] for f in trace["followed"]] == [trace["allowed"]]


@pytest.mark.asyncio
async def test_api_needs_manage_permissions(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.permission_inspector import explain_access
    from grunt.errors import APIError

    await ctx.new_doc("User", {"email": "alice@x.com", "first_name": "A", "last_name": "L"})
    await ctx.db._session().commit()
    async with grunt.context(db_session, engine, make_user("admin@x.com", is_superadmin=True)):
        trace = await explain_access("alice@x.com", "CpTask", "read", "K1")
    assert trace["doc"] == "K1" and trace["user_name"]
    async with grunt.context(db_session, engine, make_user("nobody@x.com", roles=["Reader"])):
        with pytest.raises(APIError):
            await explain_access("alice@x.com", "CpTask", "read", "K1")
