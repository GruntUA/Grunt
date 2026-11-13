"""Permissions (``grunt.permissions.perms``): code asks for a capability, a role
holds a set of them (``Role.permissions``), System Manager holds ``*``.

Roles: ``Mailer`` manages e-mail; ``Plain`` holds nothing; ``RoleEditor`` may
edit roles (a DocType rule) and manages e-mail - but can't hand out more.
"""

import pytest
from fastapi import HTTPException

from grunt.errors import ApplicationError
from grunt.permissions.perms import has_perm, user_perms
from tests.support import make_user

MAILER = make_user("mailer@x.com", roles=["Mailer"])
PLAIN = make_user("plain@x.com", roles=["Plain"])
EDITOR = make_user("editor@x.com", roles=["RoleEditor"])
ADMIN = make_user("admin@x.com", roles=["System Manager"])


@pytest.fixture
async def roles(ctx, monkeypatch):
    from grunt.metadata.permission import DocPermission
    from grunt.metadata.registry import doctype_registry

    await ctx.new_doc("Role", {"role_name": "Mailer", "permissions": ["grunt.manage_email"]})
    await ctx.new_doc("Role", {"role_name": "Plain"})
    await ctx.new_doc("Role", {"role_name": "RoleEditor", "permissions": ["grunt.manage_email"]})
    # RoleEditor may edit roles - in memory only: saving the core DocType would
    # export it over grunt/auth/doctypes/Role/Role.json.
    role = await doctype_registry.get("Role")
    rule = DocPermission(role="RoleEditor", actions=["read", "write"])
    monkeypatch.setattr(role, "permissions", [*role.permissions, rule])
    for email in ("mailer@x.com", "plain@x.com", "editor@x.com", "admin@x.com"):
        await ctx.new_doc("User", {"email": email, "first_name": "U", "last_name": "Ser"})
    await ctx.db._session().commit()


async def _as(user, call, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, user):
        return await call(grunt)


@pytest.mark.asyncio
async def test_roles_grant_permissions(roles, db_session, engine):
    async def check(g):
        return (
            await has_perm("grunt.manage_email"),
            await has_perm("grunt.manage_users"),
        )

    assert await _as(MAILER, check, db_session, engine) == (True, False)
    assert await _as(PLAIN, check, db_session, engine) == (False, False)
    assert await _as(ADMIN, check, db_session, engine) == (True, True)  # "*"


@pytest.mark.asyncio
async def test_unknown_permission_is_an_error(roles, db_session, engine):
    with pytest.raises(KeyError):
        await _as(MAILER, lambda g: has_perm("grunt.manage_emial"), db_session, engine)


@pytest.mark.asyncio
async def test_whitelist_perm(roles, db_session, engine):
    # The permission opens the method; the data it reads still follows DocType rules.
    from grunt.api.context import whitelist

    @whitelist(perm="grunt.manage_email")
    async def mail_tool() -> str:
        return "ok"

    assert getattr(mail_tool, "_required_perm", None) == "grunt.manage_email"
    assert await _as(MAILER, lambda g: mail_tool(), db_session, engine) == "ok"
    with pytest.raises(HTTPException) as exc_info:
        await _as(PLAIN, lambda g: mail_tool(), db_session, engine)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_saving_a_role_takes_effect(roles, db_session, engine):
    async def mail(g):
        return await has_perm("grunt.manage_email")

    assert await _as(PLAIN, mail, db_session, engine) is False
    await _as(
        ADMIN,
        lambda g: g.save_doc("Role", "Plain", {"permissions": ["grunt.manage_email"]}),
        db_session,
        engine,
    )
    assert await _as(PLAIN, mail, db_session, engine) is True


@pytest.mark.asyncio
async def test_nobody_grants_more_than_they_hold(roles, db_session, engine):
    # What the editor holds - fine; more - refused.
    await _as(
        EDITOR,
        lambda g: g.save_doc("Role", "Plain", {"permissions": ["grunt.manage_email"]}),
        db_session,
        engine,
    )
    for extra in (["*"], ["grunt.manage_users"]):
        with pytest.raises(HTTPException) as exc_info:
            await _as(
                EDITOR,
                lambda g, extra=extra: g.save_doc("Role", "Plain", {"permissions": extra}),
                db_session,
                engine,
            )
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_unknown_permission_on_a_role_is_refused(ctx):
    with pytest.raises((HTTPException, ApplicationError)) as exc_info:
        await ctx.new_doc("Role", {"role_name": "Typo", "permissions": ["grunt.manage_emial"]})
    status = getattr(exc_info.value, "status_code", None)
    assert status == 422


@pytest.mark.asyncio
async def test_system_user_holds_everything(ctx):
    from grunt.auth.constants import SYSTEM_USER_EMAIL

    assert await user_perms(SYSTEM_USER_EMAIL) == frozenset({"*"})


@pytest.mark.asyncio
async def test_whoami_lists_permissions(roles, db_session, engine):
    from grunt.auth.user_api import whoami

    me = await _as(MAILER, lambda g: whoami(), db_session, engine)
    assert me["permissions"] == ["grunt.manage_email"]
