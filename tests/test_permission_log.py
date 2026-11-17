"""Permission Log (PERMISSIONS_PLAN step 6b): changes of who may do what -
role assignments, role permissions, DocType rules, shares - are logged with
who made them; other changes of the same documents are not."""

import pytest

from grunt.permissions.audit import diff, summary

BOX = {
    "name": "PlBox",
    "label": "Pl Box",
    "module": "core",
    "fields": [{"fieldname": "title", "label": "Title", "fieldtype": "Data"}],
    "permissions": [
        {"role": "System Manager", "actions": ["read", "write", "create", "delete", "share"]}
    ],
}


async def _log(ctx, doctype: str, doc_id: str) -> list[dict]:
    return await ctx.db.get_all(
        "PermissionLog",
        filters={"ref_doctype": doctype, "doc_id": doc_id},
        fields=["action", "summary", "changes", "owner"],
        order_by="created_at",
        order="asc",
        limit=50,
    )


def test_table_rows_added_and_removed():
    before = {"roles": [{"role_name": "Clerk", "idx": 1, "name": "a"}]}
    after = {
        "roles": [
            {"role_name": "Clerk", "idx": 1, "name": "b"},  # same assignment, new row id
            {"role_name": "Clerk", "scope_doctype": "Department", "scope_value": "IT", "idx": 2},
        ]
    }
    changes = diff("User", before, after)
    assert changes == [
        {
            "field": "roles",
            "added": [{"role_name": "Clerk", "scope_doctype": "Department", "scope_value": "IT"}],
            "removed": [],
        }
    ]
    assert summary(changes) == "roles: + Clerk (scope_doctype=Department, scope_value=IT)"
    # Fields that don't decide access aren't compared.
    assert diff("User", {"first_name": "A"}, {"first_name": "B"}) == []


@pytest.mark.asyncio
async def test_user_roles_rules_and_shares_are_logged(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**BOX, "__is_new": True})
    await ctx.new_doc("Role", {"role_name": "PlClerk"})
    user = await ctx.new_doc(
        "User",
        {"email": "pl@example.com", "first_name": "P", "last_name": "L", "roles": []},
    )
    await ctx.save_doc(
        "User",
        user["name"],
        {"roles": [{"role_name": "PlClerk"}], "first_name": "Renamed"},
    )
    await ctx.save_doc("User", user["name"], {"last_name": "Only a name"})  # not logged

    entries = await _log(ctx, "User", user["name"])
    # A new account is an access event too; the name change alone isn't.
    assert [e["action"] for e in entries] == ["Created", "Changed"]
    assert entries[1]["summary"] == "roles: + PlClerk"
    assert entries[1]["owner"]  # who made the change

    # A DocType rule added through the DocType document.
    dt = await ctx.get_doc("DocType", "PlBox")
    rules = [*dt["permissions"], {"role": "PlClerk", "actions": ["read"]}]
    await ctx.save_doc("DocType", "PlBox", {"permissions": rules})
    [rule_entry] = [e for e in await _log(ctx, "DocType", "PlBox") if e["action"] == "Changed"]
    assert "permissions: + PlClerk" in rule_entry["summary"]

    # Role permissions.
    role = await ctx.db.get_value("Role", {"role_name": "PlClerk"}, "name")
    await ctx.save_doc("Role", role, {"permissions": ["grunt.manage_users"]})
    [perm_entry] = [e for e in await _log(ctx, "Role", role) if e["action"] == "Changed"]
    assert perm_entry["summary"] == "permissions: + grunt.manage_users"

    # A share: created, then deleted.
    box = await ctx.new_doc("PlBox", {"title": "B"})
    share = await ctx.new_doc(
        "SharedWith",
        {"reference_doctype": "PlBox", "reference_id": box["name"], "user": "pl@example.com"},
    )
    await ctx.delete_doc("SharedWith", share["name"])
    actions = [e["action"] for e in await _log(ctx, "SharedWith", share["name"])]
    assert actions == ["Created", "Deleted"]


@pytest.mark.asyncio
async def test_log_is_read_only_for_people(ctx, db_session, engine):
    import grunt
    from grunt.errors import APIError
    from tests.support import make_user

    async with grunt.context(db_session, engine, make_user("adm@example.com", is_superadmin=True)):
        with pytest.raises(APIError):
            await grunt.new_doc("PermissionLog", {"ref_doctype": "User", "doc_id": "x"})


@pytest.mark.asyncio
async def test_rules_saved_past_the_document_pipeline_are_logged(ctx):
    """``save_doctype`` / ``delete_doctype`` store the definition through the
    registry, not the document pipeline - their rule changes are logged too."""
    from grunt.api.v1.meta import delete_doctype, save_doctype

    box = {**BOX, "name": "PlDirect", "label": "Pl Direct"}
    await save_doctype(doctype_data={**box, "__is_new": True})
    await save_doctype(
        doctype_data={
            **box,
            "permissions": [*box["permissions"], {"role": "All", "actions": ["read"]}],
        }
    )
    await save_doctype(doctype_data={**box, "label": "Renamed"})  # rules as before the last one
    await delete_doctype(name="PlDirect")

    entries = await _log(ctx, "DocType", "PlDirect")
    assert [e["action"] for e in entries] == ["Created", "Changed", "Changed", "Deleted"]
    assert entries[1]["summary"].startswith("permissions: + All")
    assert entries[2]["summary"].startswith("permissions: − All")
