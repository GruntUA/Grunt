"""Tests for the grunt.permissions engine.

Three collaborating pieces, previously in three separate files:

* ``grunt.permissions.match.PermissionMatch`` — the single parser/evaluator
  shared by row-level query filtering (``to_sql``) and per-document checks
  (``evaluate``).
* ``grunt.permissions.access.RoleAccess`` — "is this user exempt from
  checks" and "which permission rows match their roles".
* ``grunt.permissions.query.apply_permission_filter`` — row-level ``match``
  SQL filter, which composes the two above.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, MetaData, String, Table, false, select

from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.query import apply_permission_filter
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


@pytest.fixture(autouse=True)
def _no_document_shares(monkeypatch):
    """Role logic in isolation — SharedWith grants are covered by tests/test_doc_shares.py."""
    from grunt.permissions import shares

    async def _no_share(*_a, **_kw):
        return False

    async def _no_clause(*_a, **_kw):
        return None

    monkeypatch.setattr(shares, "has_share", _no_share)
    monkeypatch.setattr(shares, "shared_names_clause", _no_clause)


_META = MetaData()
_TABLE = Table(
    "perm_engine_test_table",
    _META,
    Column("name", String, primary_key=True),
    Column("owner", String),
    Column("status", String),
)


def _user(
    email: str = "user@example.com",
    roles: list[str] | None = None,
    is_superadmin: bool = False,
) -> User:
    return make_user(email, roles=roles or [], is_superadmin=is_superadmin)


def _system_user() -> User:
    """The internal SYSTEM_USER identity — the only thing RoleAccess.is_unrestricted
    is True for (see grunt/permissions/access.py). A human holding "System
    Manager" is scoped by matching permission rows like anyone else."""
    from grunt.auth.doctypes.User.user import SYSTEM_USER

    return SYSTEM_USER


def _doctype(perms: list[dict]) -> DocType:
    return DocType(
        name="PermTest",
        label="Perm Test",
        module="test",
        fields=[],
        permissions=[DocPermission(**p) for p in perms],
    )


# ── PermissionMatch.to_sql ────────────────────────────────────────────────


class TestPermissionMatchToSql:
    async def test_owner_eq_user(self):
        cond = await PermissionMatch("owner == user").to_sql(_TABLE, _user("alice@example.com"))
        assert cond is not None
        assert "alice@example.com" in str(cond.compile(compile_kwargs={"literal_binds": True}))

    async def test_status_eq_literal(self):
        cond = await PermissionMatch("status == 'Published'").to_sql(
            _TABLE, _user("alice@example.com")
        )
        assert cond is not None
        assert "Published" in str(cond.compile(compile_kwargs={"literal_binds": True}))

    async def test_not_equal(self):
        cond = await PermissionMatch("status != 'Archived'").to_sql(
            _TABLE, _user("alice@example.com")
        )
        assert cond is not None

    async def test_unknown_field_is_none(self):
        cond = await PermissionMatch("nonexistent == user").to_sql(
            _TABLE, _user("alice@example.com")
        )
        assert cond is None

    async def test_boolean_logic_is_unparseable(self):
        m = PermissionMatch("owner == user and status == 'Open'")
        assert await m.to_sql(_TABLE, _user("alice@example.com")) is None

    async def test_numeric_literal_is_unparseable(self):
        cond = await PermissionMatch("status == 5").to_sql(_TABLE, _user("alice@example.com"))
        assert cond is None

    async def test_dotted_path_without_doctype_is_none(self):
        """A ``link.field`` expression can't be translated without the DocType
        that owns the Link — fail closed, don't leak."""
        m = PermissionMatch("asset_user.user_id == user")
        assert await m.to_sql(_TABLE, _user("alice@example.com")) is None

    async def test_deep_path_is_unparseable(self):
        """Only a single hop is supported; ``a.b.c`` never parses."""
        m = PermissionMatch("a.b.c == user")
        assert m._parsed is None
        assert await m.to_sql(_TABLE, _user("alice@example.com")) is None


# ── PermissionMatch.evaluate ─────────────────────────────────────────────


class TestPermissionMatchEvaluate:
    def test_owner_eq_user_true(self):
        m = PermissionMatch("owner == user")
        assert m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    def test_owner_eq_user_false(self):
        m = PermissionMatch("owner == user")
        assert not m.evaluate({"owner": "bob@example.com"}, _user("alice@example.com"))

    def test_boolean_logic_supported(self):
        """evaluate() supports full simpleeval syntax, wider than to_sql()'s
        narrow "field == value" form — that's the whole point of having two
        evaluation modes instead of forcing one.
        """
        m = PermissionMatch("owner == user and doc.get('status') == 'Open'")
        doc = {"owner": "alice@example.com", "status": "Open"}
        assert m.evaluate(doc, _user("alice@example.com"))

    def test_eval_error_fails_closed(self):
        """A broken/unsupported expression must deny, not grant."""
        m = PermissionMatch("doc.this_field_does_not_exist")
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    @pytest.mark.parametrize("expr", ["", "   "])
    def test_empty_expression_denies(self, expr):
        m = PermissionMatch(expr)
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))

    def test_field_named_user_is_not_shadowed_by_current_user_token(self):
        """Regression: a field literally named `user` (the natural field
        name for "who this row belongs to" on DocTypes like PushSubscription/
        Notification) used to collide with the reserved `user` name meaning
        "current user's email" in evaluate()'s simpleeval namespace — the
        doc's own `user` field was never consulted, so "user == user" was
        always True regardless of the document's actual owner.
        """
        m = PermissionMatch("user == user")
        assert m.evaluate({"user": "alice@example.com"}, _user("alice@example.com"))
        assert not m.evaluate({"user": "bob@example.com"}, _user("alice@example.com"))

    def test_narrow_form_denies_when_field_missing_from_doc(self):
        m = PermissionMatch("status == 'Open'")
        assert not m.evaluate({"owner": "alice@example.com"}, _user("alice@example.com"))


# ── RoleAccess ───────────────────────────────────────────────────────────


class TestRoleAccess:
    def test_system_user_is_unrestricted(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = RoleAccess(dt, _system_user())
        assert access.is_unrestricted
        assert access.matching_permissions() == []

    def test_system_manager_role_alone_is_not_unrestricted(self):
        """A human holding "System Manager" is scoped by matching permission
        rows, not an unconditional bypass — only the internal SYSTEM_USER
        identity is (see test_system_user_is_unrestricted)."""
        dt = _doctype([{"role": "Employee", "read": True}])
        access = RoleAccess(dt, _user(roles=["System Manager"]))
        assert not access.is_unrestricted
        assert access.matching_permissions() == []

    def test_no_permissions_defined_is_restricted(self):
        """Deny-by-default: no permission rows means nobody has been granted
        access yet, not "open to anyone logged in". Only the internal
        SYSTEM_USER identity bypasses."""
        dt = DocType(name="Closed", label="Closed", module="test", fields=[])
        access = RoleAccess(dt, _user(roles=["Employee"]))
        assert not access.is_unrestricted
        assert access.matching_permissions() == []

    def test_matching_role_returned(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = RoleAccess(dt, _user(roles=["Employee"]))
        assert not access.is_unrestricted
        matched = access.matching_permissions()
        assert len(matched) == 1
        assert matched[0].role == "Employee"

    def test_non_matching_role_excluded(self):
        dt = _doctype([{"role": "Manager", "read": True}])
        access = RoleAccess(dt, _user(roles=["Employee"]))
        assert access.matching_permissions() == []

    def test_all_role_always_matches(self):
        dt = _doctype([{"role": "All", "read": True}])
        access = RoleAccess(dt, _user(roles=[]))
        assert len(access.matching_permissions()) == 1

    def test_multiple_roles_only_matching_returned(self):
        dt = _doctype(
            [
                {"role": "Employee", "read": True},
                {"role": "Manager", "write": True},
                {"role": "All", "read": True},
            ]
        )
        access = RoleAccess(dt, _user(roles=["Employee"]))
        assert {p.role for p in access.matching_permissions()} == {"Employee", "All"}

    def test_user_roles_exposed_as_frozenset(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = RoleAccess(dt, _user(roles=["Employee", "Viewer"]))
        assert access.user_roles == frozenset({"Employee", "Viewer"})


# ── apply_permission_filter (composes the two above) ─────────────────────


class TestApplyPermissionFilter:
    async def test_system_user_unfiltered(self):
        dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
        query = await apply_permission_filter(select(_TABLE), _TABLE, _system_user(), dt)
        assert query.whereclause is None

    async def test_no_permissions_defined_denies_all_rows(self):
        """Deny-by-default: no permission rows means no role matched, so the
        query is filtered to zero rows rather than left unfiltered."""
        dt = DocType(name="Closed", label="Closed", module="test", fields=[])
        user = _user("bob@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        expected = select(_TABLE).where(false()).whereclause
        assert query.whereclause is not None
        assert expected is not None
        assert query.whereclause.compare(expected)

    async def test_rule_without_match_is_unrestricted(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        user = _user("bob@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        assert query.whereclause is None

    async def test_owner_eq_user_filters_to_own_rows(self):
        dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
        user = _user("alice@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        assert query.whereclause is not None
        assert "alice@example.com" in str(query.compile(compile_kwargs={"literal_binds": True}))

    async def test_unparseable_match_fails_closed_not_open(self):
        """Regression: an expression the mini-parser can't translate used to make
        apply_permission_filter treat the rule as unrestricted (return everything).
        It must instead exclude all rows for that rule rather than leak them.
        """
        dt = _doctype(
            [{"role": "Employee", "read": True, "match": "owner == user and status == 'Open'"}]
        )
        user = _user("alice@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        assert query.whereclause is not None

    async def test_no_matching_role_fails_closed(self):
        dt = _doctype([{"role": "Manager", "read": True, "match": "owner == user"}])
        user = _user("bob@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        assert query.whereclause is not None

    async def test_two_match_rules_or_together(self):
        """Several read rules with a translatable ``match`` widen access (OR):
        a row visible if I own it *or* its status is Published."""
        dt = _doctype(
            [
                {"role": "Employee", "read": True, "match": "owner == user"},
                {"role": "Employee", "read": True, "match": "status == 'Published'"},
            ]
        )
        user = _user("alice@example.com", roles=["Employee"])
        query = await apply_permission_filter(select(_TABLE), _TABLE, user, dt)
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert " OR " in sql.upper()
        assert "alice@example.com" in sql and "Published" in sql
