"""Tests for grunt.permissions.query (row-level `match` SQL filter)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import Column, MetaData, String, Table, false, select

from grunt.metadata.doctype import DocType
from grunt.metadata.permission import DocTypePermission
from grunt.permissions.query import apply_permission_filter
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

_META = MetaData()
_TABLE = Table(
    "perm_test_table",
    _META,
    Column("name", String, primary_key=True),
    Column("owner", String),
    Column("status", String),
)


def _user(email: str, roles: list[str], is_superadmin: bool = False) -> User:
    return make_user(email, roles=roles, is_superadmin=is_superadmin)


def _doctype(perms: list[dict]) -> DocType:
    return DocType(
        name="PermTest",
        label="Perm Test",
        module="test",
        fields=[],
        permissions=[DocTypePermission(**p) for p in perms],
    )


def test_superadmin_unfiltered():
    dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
    user = _user("admin@example.com", [], is_superadmin=True)
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is None


def test_no_permissions_defined_denies_all_rows():
    """Deny-by-default: no permission rows means no role matched, so the
    query is filtered to zero rows rather than left unfiltered."""
    dt = DocType(name="Closed", label="Closed", module="test", fields=[])
    user = _user("bob@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    expected = select(_TABLE).where(false()).whereclause
    assert query.whereclause is not None
    assert expected is not None
    assert query.whereclause.compare(expected)


def test_rule_without_match_is_unrestricted():
    dt = _doctype([{"role": "Employee", "read": True}])
    user = _user("bob@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is None


def test_owner_eq_user_filters_to_own_rows():
    dt = _doctype([{"role": "Employee", "read": True, "match": "owner == user"}])
    user = _user("alice@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is not None
    compiled = query.compile(compile_kwargs={"literal_binds": True})
    assert "alice@example.com" in str(compiled)


def test_status_eq_literal_filters():
    dt = _doctype([{"role": "Viewer", "read": True, "match": "status == 'Published'"}])
    user = _user("bob@example.com", ["Viewer"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    compiled = query.compile(compile_kwargs={"literal_binds": True})
    assert "Published" in str(compiled)


def test_unparseable_match_fails_closed_not_open():
    """Regression: an expression the mini-parser can't translate used to make
    apply_permission_filter treat the rule as unrestricted (return everything).
    It must instead exclude all rows for that rule rather than leak them.
    """
    dt = _doctype(
        [{"role": "Employee", "read": True, "match": "owner == user and status == 'Open'"}]
    )
    user = _user("alice@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is not None


def test_no_matching_role_fails_closed():
    dt = _doctype([{"role": "Manager", "read": True, "match": "owner == user"}])
    user = _user("bob@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is not None


@pytest.mark.parametrize(
    "expr",
    ["owner != user", "status != 'Archived'"],
)
def test_not_equal_supported(expr):
    dt = _doctype([{"role": "Employee", "read": True, "match": expr}])
    user = _user("alice@example.com", ["Employee"])
    query = apply_permission_filter(select(_TABLE), _TABLE, user, dt)
    assert query.whereclause is not None
