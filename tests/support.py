"""Shared test doubles.

Not a conftest.py — deliberately a plain module, since conftest.py files get
pytest's special auto-discovery/import handling and this project has already
hit double-import issues from that (see conftest.py:db_session docstring).
A regular module avoids that entirely: import it like any other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User


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
