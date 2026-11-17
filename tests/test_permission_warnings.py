"""Access settings that probably don't do what was meant (PERMISSIONS_PLAN
step 6d) - shown on the DocType and Role forms, never blocking a save."""

import pytest

from grunt.metadata.doctype import DocType
from grunt.permissions.warnings import doctype_warnings, role_warnings


def _dt(permissions: list[dict], **extra) -> DocType:
    return DocType.model_validate(
        {
            "name": "WarnBox",
            "label": "Warn Box",
            "module": "core",
            "fields": [
                {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
                {"fieldname": "salary", "label": "Salary", "fieldtype": "Currency"},
            ],
            "permissions": permissions,
            **extra,
        }
    )


async def _codes(dt: DocType) -> list[str]:
    return [w["code"] for w in await doctype_warnings(dt)]


@pytest.mark.asyncio
async def test_doctype_warnings(ctx):
    assert await _codes(_dt([])) == ["no_rules"]
    assert await _codes(_dt([], is_child=True)) == []  # child rows follow the parent

    await ctx.new_doc("Role", {"role_name": "WarnNobody"})
    await ctx.new_doc("Role", {"role_name": "WarnHeld"})
    await ctx.new_doc(
        "User",
        {
            "email": "held@example.com",
            "first_name": "H",
            "last_name": "D",
            "roles": [{"role_name": "WarnHeld"}],
        },
    )
    await ctx.db._session().commit()
    warnings = await doctype_warnings(
        _dt(
            [
                {"role": "All", "actions": ["read"], "hidden_fields": ["salary"]},
                {"role": "WarnNobody", "actions": []},
            ]
        )
    )
    assert [w["code"] for w in warnings] == [
        "rule_grants_nothing",
        "role_without_users",
        "field_hidden_from_all",
    ]
    assert "Salary" in warnings[-1]["message"]

    # Hidden for one reader only - someone still sees it; All isn't "without users".
    assert (
        await _codes(
            _dt(
                [
                    {"role": "All", "actions": ["read"], "hidden_fields": ["salary"]},
                    {"role": "WarnHeld", "actions": ["read", "write"]},
                ]
            )
        )
        == []
    )

    # Read-only for everyone who may change it.
    assert await _codes(
        _dt([{"role": "All", "actions": ["read", "write"], "readonly_fields": ["title"]}])
    ) == ["field_readonly_for_all"]


@pytest.mark.asyncio
async def test_role_warnings(ctx):
    await ctx.new_doc("Role", {"role_name": "WarnEmpty"})
    await ctx.new_doc(
        "User",
        {
            "email": "warn@example.com",
            "first_name": "W",
            "last_name": "R",
            "roles": [{"role_name": "WarnEmpty"}],
        },
    )
    await ctx.new_doc("Role", {"role_name": "WarnUnheld", "permissions": ["grunt.manage_users"]})
    await ctx.db._session().commit()

    assert [w["code"] for w in await role_warnings("WarnEmpty")] == ["role_grants_nothing"]
    assert [w["code"] for w in await role_warnings("WarnUnheld")] == ["role_without_users"]
    assert await role_warnings("System Manager") == []
    assert await role_warnings("All") == []


@pytest.mark.asyncio
async def test_endpoints_need_manage_permissions(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.permission_warnings import for_doctype
    from grunt.errors import APIError
    from tests.support import make_user

    async with grunt.context(db_session, engine, make_user("adm@x.com", is_superadmin=True)):
        assert isinstance(await for_doctype("User"), list)
    async with grunt.context(db_session, engine, make_user("nobody@x.com")):
        with pytest.raises(APIError):
            await for_doctype("User")
