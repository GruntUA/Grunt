"""Shared test doubles.

Not a conftest.py — deliberately a plain module, since conftest.py files get
pytest's special auto-discovery/import handling and this project has already
hit double-import issues from that (see conftest.py:db_session docstring).
A regular module avoids that entirely: import it like any other.
"""

import contextlib
from collections.abc import Iterator
from typing import Any

from grunt.local import _user_ctx
lazy from grunt.auth.doctypes.User.user import User
lazy from grunt.permissions.rbac import permission_checker


def make_user(email: str, roles: list[str] | None = None, is_superadmin: bool = False) -> User:
    """Build a real, unsaved `User` Document for tests to act as.

    ``is_superadmin=True`` grants full admin rights the same way it does in
    production: by adding the "System Manager" role, not via a stored flag
    (there is no such field on `User` anymore).

    Cheap despite being "real": `Document.__init__` only stores the data
    dict on the instance — no DocType/DB lookup happens at construction, so
    this doesn't touch the database (unlike driving a *target* doctype
    through the facade for a core DocType already seeded on the live site —
    see project notes on DocTypeRegistry._lazy_load()).
    """
    from grunt.auth.doctypes.User.user import User as _User

    role_list = list(roles or [])
    if is_superadmin and "System Manager" not in role_list:
        role_list.append("System Manager")
    return _User(doctype="User", data={"email": email, "roles": role_list})


@contextlib.contextmanager
def acting_as(user: Any) -> Iterator[None]:
    """Run the block as *user* (a ``User`` document), as ``frappe.set_user``.

    Permission checks read the current user from the context, so a user that
    exists only in memory (:func:`make_user`) is checked by acting as them.
    """
    token = _user_ctx.set(user)
    try:
        yield
    finally:
        _user_ctx.reset(token)


async def check_as(user: Any, *args: Any, **kwargs: Any) -> bool:
    """``permission_checker.check(*args)`` for *user* (see :func:`acting_as`)."""
    with acting_as(user):
        return await permission_checker.check(user, *args, **kwargs)


async def require_as(user: Any, *args: Any, **kwargs: Any) -> None:
    """``permission_checker.require(*args)`` for *user* (see :func:`acting_as`)."""
    with acting_as(user):
        await permission_checker.require(user, *args, **kwargs)


async def hidden_fields_as(user: Any, doctype: Any) -> frozenset[str]:
    """``permission_checker.hidden_fields(doctype)`` for *user* (see :func:`acting_as`)."""
    with acting_as(user):
        return permission_checker.hidden_fields(user, doctype)


async def read_predicate_as(user: Any, meta: Any) -> Any:
    """``read_predicate`` of *user* (see :func:`acting_as`)."""
    from grunt.permissions.query import read_predicate

    with acting_as(user):
        return await read_predicate(user, meta)


def access_of(doctype: Any, user: Any) -> Any:
    """``RoleAccess`` of an in-memory *user*."""
    from grunt.permissions.access import RoleAccess

    return RoleAccess(doctype, user)
