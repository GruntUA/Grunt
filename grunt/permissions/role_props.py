"""Properties of the Role documents themselves - permissions, ``disabled``,
``site_only``, ``home_page`` - loaded for every role of a site at once (roles
are few) and cached per process until a Role is saved or deleted.

Below :mod:`grunt.permissions.roles` (which drops disabled roles from what a
user holds), so it imports nothing from the permission layer.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from grunt.cache.bus import fanout
from grunt.db.api import GruntDB
from grunt.db.commit import on_commit
from grunt.local import _session_ctx
from grunt.site.manager import site_cache_key

_db = GruntDB()  # stateless: reads through the context's session

#: Roles that can't be disabled or made site-only: the administrator's and the
#: built-in principals.
PROTECTED_ROLES = frozenset({"System Manager", "All", "Guest"})


@dataclass(frozen=True)
class RoleProps:
    permissions: frozenset[str]
    disabled: bool
    site_only: bool
    home_page: str | None


# {site: {role: props}}
_ROLES: dict[str, dict[str, RoleProps]] = {}
# Bumped on every invalidation: a load that started before one doesn't store
# what it read (the rows may predate the change).
_epoch = 0


@fanout
def invalidate_roles(site: str | None = None) -> None:
    """Drop the cached roles of *site* (``None`` - every site). Called from the
    Role controller after save / delete - inside its transaction, so the cache
    is dropped again once it commits: a request reading the Role rows in
    between still saw the old ones (other processes hear of it only after the
    commit, through the bus)."""
    _evict(site)

    async def after_commit() -> None:
        _evict(site)

    on_commit(after_commit)


def _evict(site: str | None) -> None:
    global _epoch
    _epoch += 1
    if site is None:
        _ROLES.clear()
    else:
        _ROLES.pop(site, None)


async def role_props() -> dict[str, RoleProps]:
    """``{role: props}`` of the context's site."""
    key = site_cache_key()
    cached = _ROLES.get(key)
    if cached is not None:
        return cached
    epoch = _epoch
    rows = await _db.get_all(
        "Role",
        fields=["name", "permissions", "disabled", "site_only", "home_page"],
        limit=None,
    )
    loaded = {
        r.name: RoleProps(
            permissions=frozenset(r.permissions or []),
            disabled=bool(r.disabled),
            site_only=bool(r.site_only),
            home_page=(r.home_page or "").strip() or None,
        )
        for r in rows
    }
    if epoch == _epoch:
        _ROLES[key] = loaded
    return loaded


async def disabled_roles() -> frozenset[str]:
    """Names of the site's disabled roles - empty with no database in context."""
    if _session_ctx.get() is None:
        return frozenset()
    return frozenset(name for name, p in (await role_props()).items() if p.disabled)


async def without_disabled(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Role assignment *rows* minus those of disabled roles: a disabled role
    stays in the users' tables but gives them nothing."""
    disabled = await disabled_roles()
    return [r for r in rows if r.get("role_name") not in disabled]
