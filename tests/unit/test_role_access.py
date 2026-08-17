"""Tests for grunt.permissions.access.RoleAccess.

Extracted from three places (rbac.py:check, rbac.py:hidden_fields,
query.py:apply_permission_filter) that each independently re-derived
"is this user exempt from checks" and "which permission rows match their
roles" — the same two facts, computed three different ways.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from grunt.metadata.doctype import DocType, DocTypePermission
from grunt.permissions.access import RoleAccess
from tests.support import make_user

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


def _user(roles: list[str], is_superadmin: bool = False) -> User:
    return make_user("user@example.com", roles=roles, is_superadmin=is_superadmin)


def _doctype(perms: list[dict]) -> DocType:
    return DocType(
        name="AccessTest",
        label="Access Test",
        module="test",
        fields=[],
        permissions=[DocTypePermission(**p) for p in perms],
    )


def test_superadmin_is_unrestricted():
    dt = _doctype([{"role": "Employee", "read": True}])
    access = RoleAccess(dt, _user([], is_superadmin=True))
    assert access.is_unrestricted
    assert access.matching_permissions() == []


def test_no_permissions_defined_is_unrestricted():
    dt = DocType(name="Open", label="Open", module="test", fields=[])
    access = RoleAccess(dt, _user(["Employee"]))
    assert access.is_unrestricted


def test_matching_role_returned():
    dt = _doctype([{"role": "Employee", "read": True}])
    access = RoleAccess(dt, _user(["Employee"]))
    assert not access.is_unrestricted
    matched = access.matching_permissions()
    assert len(matched) == 1
    assert matched[0].role == "Employee"


def test_non_matching_role_excluded():
    dt = _doctype([{"role": "Manager", "read": True}])
    access = RoleAccess(dt, _user(["Employee"]))
    assert access.matching_permissions() == []


def test_all_role_always_matches():
    dt = _doctype([{"role": "All", "read": True}])
    access = RoleAccess(dt, _user([]))
    assert len(access.matching_permissions()) == 1


def test_multiple_roles_only_matching_returned():
    dt = _doctype(
        [
            {"role": "Employee", "read": True},
            {"role": "Manager", "write": True},
            {"role": "All", "read": True},
        ]
    )
    access = RoleAccess(dt, _user(["Employee"]))
    matched_roles = {p.role for p in access.matching_permissions()}
    assert matched_roles == {"Employee", "All"}


def test_user_roles_exposed_as_frozenset():
    dt = _doctype([{"role": "Employee", "read": True}])
    access = RoleAccess(dt, _user(["Employee", "Viewer"]))
    assert access.user_roles == frozenset({"Employee", "Viewer"})
