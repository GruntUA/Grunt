"""Tests for the grunt.permissions engine.

Three collaborating pieces, previously in three separate files:

* ``grunt.permissions.match.PermissionMatch`` — the single parser/evaluator
  shared by row-level query filtering (``to_expr``) and per-document checks
  (``evaluate``).
* ``grunt.permissions.access.RoleAccess`` — "is this user exempt from
  checks" and "which permission rows match their roles".
* ``grunt.permissions.query.read_predicate`` — the row-level predicate,
  which composes the two above.
"""

import pytest
from sqlalchemy import Column, MetaData, String, Table

from grunt.document.meta import Meta
from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocPermission
from grunt.permissions.match import PermissionMatch
from grunt.query.nodes import FALSE, TRUE, Cmp, Or
from tests.support import access_of, check_as, make_user, read_predicate_as
lazy from grunt.auth.doctypes.User.user import User


@pytest.fixture(autouse=True)
def _no_document_shares(monkeypatch):
    """Role logic in isolation — SharedWith grants are covered by tests/test_doc_shares.py."""
    from grunt.permissions import query, shares

    async def _no_share(*_a, **_kw):
        return False

    async def _no_clause(*_a, **_kw):
        return None

    monkeypatch.setattr(shares, "has_share", _no_share)
    monkeypatch.setattr(shares, "shared_predicate", _no_clause)
    monkeypatch.setattr(query, "shared_predicate", _no_clause)


_META = MetaData()
_TABLE = Table(
    "perm_engine_test_table",
    _META,
    Column("name", String, primary_key=True),
    Column("owner", String),
    Column("status", String),
)
_COLUMNS = frozenset(_TABLE.c.keys())


def _meta(dt: DocType) -> Meta:
    """*dt* as a Meta whose rows hold ``_TABLE``'s columns."""
    meta = Meta(dt)
    meta._columns = _COLUMNS
    return meta


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


# ── PermissionMatch.to_expr ───────────────────────────────────────────────


class TestPermissionMatchToExpr:
    async def test_owner_eq_user(self):
        expr = await PermissionMatch("owner == user").to_expr(_COLUMNS, "alice@example.com")
        assert expr == Cmp("owner", "eq", "alice@example.com")

    async def test_status_eq_literal(self):
        expr = await PermissionMatch("status == 'Published'").to_expr(_COLUMNS, "alice@example.com")
        assert expr == Cmp("status", "eq", "Published")

    async def test_not_equal(self):
        expr = await PermissionMatch("status != 'Archived'").to_expr(_COLUMNS, "alice@example.com")
        assert expr == Cmp("status", "ne", "Archived")

    async def test_unknown_field_is_none(self):
        expr = await PermissionMatch("nonexistent == user").to_expr(_COLUMNS, "alice@example.com")
        assert expr is None

    async def test_boolean_logic_is_unparseable(self):
        m = PermissionMatch("owner == user and status == 'Open'")
        assert await m.to_expr(_COLUMNS, "alice@example.com") is None

    async def test_numeric_literal_is_unparseable(self):
        expr = await PermissionMatch("status == 5").to_expr(_COLUMNS, "alice@example.com")
        assert expr is None

    async def test_dotted_path_without_doctype_is_none(self):
        """A ``link.field`` expression can't be translated without the DocType
        that owns the Link — fail closed, don't leak."""
        m = PermissionMatch("asset_user.user_id == user")
        assert await m.to_expr(_COLUMNS, "alice@example.com") is None

    async def test_deep_path_is_unparseable(self):
        """Only a single hop is supported; ``a.b.c`` never parses."""
        m = PermissionMatch("a.b.c == user")
        assert m._parsed is None
        assert await m.to_expr(_COLUMNS, "alice@example.com") is None


# ── A single document: the read predicate evaluated against its row ─────


async def _opens(dt: DocType, doc: dict, user: User, columns=_COLUMNS) -> bool:

    meta = Meta(dt)
    meta._columns = frozenset(columns)
    return await check_as(user, meta, "read", doc)


@pytest.mark.asyncio
class TestRowDecision:
    async def test_owner_eq_user(self):
        dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
        alice = _user("alice@example.com", roles=["Employee"])
        assert await _opens(dt, {"owner": "alice@example.com"}, alice)
        assert not await _opens(dt, {"owner": "bob@example.com"}, alice)

    async def test_rules_or_together(self):
        dt = _doctype(
            [
                {"role": "Employee", "read": True, "match": "owner == user"},
                {"role": "Employee", "read": True, "match": "status == 'Open'"},
            ]
        )
        alice = _user("alice@example.com", roles=["Employee"])
        assert await _opens(dt, {"owner": "bob@example.com", "status": "Open"}, alice)
        assert not await _opens(dt, {"owner": "bob@example.com", "status": "Closed"}, alice)

    async def test_field_named_user_is_not_shadowed_by_current_user_token(self):
        """Regression: a field literally named `user` (PushSubscription,
        Notification) once collided with the `user` token meaning "current
        user's email" - "user == user" was always True. The predicate compares
        the document's `user` column with the current user's email."""
        dt = _doctype([{"role": "Employee", "read": True, "match": "user == user"}])
        alice = _user("alice@example.com", roles=["Employee"])
        columns = {*_COLUMNS, "user"}
        assert await _opens(dt, {"user": "alice@example.com"}, alice, columns)
        assert not await _opens(dt, {"user": "bob@example.com"}, alice, columns)

    async def test_field_missing_from_doc_denies(self):
        """A field the row doesn't carry is NULL - no comparison holds."""
        dt = _doctype([{"role": "Employee", "read": True, "match": "status == 'Open'"}])
        alice = _user("alice@example.com", roles=["Employee"])
        assert not await _opens(dt, {"owner": "alice@example.com"}, alice)

    async def test_rule_on_unknown_field_denies(self):
        """A rule on a field the DocType doesn't have can't be enforced - it
        grants nothing, in a list and for one document alike."""
        dt = _doctype([{"role": "Employee", "read": True, "match": "nonexistent == user"}])
        alice = _user("alice@example.com", roles=["Employee"])
        assert not await _opens(dt, {"owner": "alice@example.com"}, alice)


# ── RoleAccess ───────────────────────────────────────────────────────────


class TestRoleAccess:
    def test_system_user_is_unrestricted(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = access_of(dt, _system_user())
        assert access.is_unrestricted
        assert access.matching_permissions() == []

    def test_system_manager_role_alone_is_not_unrestricted(self):
        """A human holding "System Manager" is scoped by matching permission
        rows, not an unconditional bypass — only the internal SYSTEM_USER
        identity is (see test_system_user_is_unrestricted)."""
        dt = _doctype([{"role": "Employee", "read": True}])
        access = access_of(dt, _user(roles=["System Manager"]))
        assert not access.is_unrestricted
        assert access.matching_permissions() == []

    def test_no_permissions_defined_is_restricted(self):
        """Deny-by-default: no permission rows means nobody has been granted
        access yet, not "open to anyone logged in". Only the internal
        SYSTEM_USER identity bypasses."""
        dt = DocType(name="Closed", label="Closed", module="test", fields=[])
        access = access_of(dt, _user(roles=["Employee"]))
        assert not access.is_unrestricted
        assert access.matching_permissions() == []

    def test_matching_role_returned(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = access_of(dt, _user(roles=["Employee"]))
        assert not access.is_unrestricted
        matched = access.matching_permissions()
        assert len(matched) == 1
        assert matched[0].role == "Employee"

    def test_non_matching_role_excluded(self):
        dt = _doctype([{"role": "Manager", "read": True}])
        access = access_of(dt, _user(roles=["Employee"]))
        assert access.matching_permissions() == []

    def test_all_role_always_matches(self):
        dt = _doctype([{"role": "All", "read": True}])
        access = access_of(dt, _user(roles=[]))
        assert len(access.matching_permissions()) == 1

    def test_multiple_roles_only_matching_returned(self):
        dt = _doctype(
            [
                {"role": "Employee", "read": True},
                {"role": "Manager", "write": True},
                {"role": "All", "read": True},
            ]
        )
        access = access_of(dt, _user(roles=["Employee"]))
        assert {p.role for p in access.matching_permissions()} == {"Employee", "All"}

    def test_user_roles_exposed_as_frozenset(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        access = access_of(dt, _user(roles=["Employee", "Viewer"]))
        assert access.user_roles == frozenset({"Employee", "Viewer"})


# ── read_predicate (composes the two above) ──────────────────────────────


class TestReadPredicate:
    async def test_system_user_unfiltered(self):
        dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
        assert await read_predicate_as(_system_user(), _meta(dt)) == TRUE

    async def test_no_permissions_defined_denies_all_rows(self):
        """Deny-by-default: no permission rows means no role matched, so no
        row is readable rather than every row."""
        dt = DocType(name="Closed", label="Closed", module="test", fields=[])
        user = _user("bob@example.com", roles=["Employee"])
        assert await read_predicate_as(user, _meta(dt)) == FALSE

    async def test_rule_without_match_is_unrestricted(self):
        dt = _doctype([{"role": "Employee", "read": True}])
        user = _user("bob@example.com", roles=["Employee"])
        assert await read_predicate_as(user, _meta(dt)) == TRUE

    async def test_owner_eq_user_filters_to_own_rows(self):
        dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
        user = _user("alice@example.com", roles=["Employee"])
        assert await read_predicate_as(user, _meta(dt)) == Cmp("owner", "eq", "alice@example.com")

    async def test_unparseable_match_fails_closed_not_open(self):
        """Regression: an expression the mini-parser can't translate used to
        be treated as unrestricted (return everything). It must instead
        exclude all rows for that rule rather than leak them.
        """
        dt = _doctype([{"role": "Employee", "read": True, "match": "nonexistent == user"}])
        user = _user("alice@example.com", roles=["Employee"])
        assert await read_predicate_as(user, _meta(dt)) == FALSE

    async def test_no_matching_role_fails_closed(self):
        dt = _doctype([{"role": "Manager", "read": True, "match": "owner == user"}])
        user = _user("bob@example.com", roles=["Employee"])
        assert await read_predicate_as(user, _meta(dt)) == FALSE

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
        assert await read_predicate_as(user, _meta(dt)) == Or(
            (Cmp("owner", "eq", "alice@example.com"), Cmp("status", "eq", "Published"))
        )
