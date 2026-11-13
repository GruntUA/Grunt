"""Permissions - what code checks instead of role names.

A role is a set of permissions (``Role.permissions``); code asks for the
permission, never for a role::

    @grunt.whitelist(perm="grunt.manage_email")
    async def send_test_email(...): ...

    if await grunt.has_perm("grunt.moderate_comments"):
        ...

so an administrator can hand out one capability ("manage e-mail") without
handing out everything System Manager holds. ``*`` grants every permission -
System Manager holds it; the internal SYSTEM_USER has it implicitly.

The core registers its permissions here, an app in its ``hooks.py``::

    permissions = [
        {"name": "inventory.manage_assets", "label": "Manage assets"},
    ]

Checking a permission nobody registered is a programming error (``KeyError``),
not a silent "no" - a misspelt name would otherwise lock everyone out without
a word, and an administrator could never grant it.
"""

from dataclasses import dataclass

from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.cache.bus import fanout
from grunt.db.api import GruntDB
from grunt.i18n import N_, _
from grunt.local import _session_ctx, session_user
from grunt.metadata.dynamic_options import register_option_provider
from grunt.permissions.roles import get_roles
from grunt.site.manager import site_cache_key

_db = GruntDB()  # stateless: reads through the context's session

#: Grants every permission.
ALL = "*"

#: ``Role.permissions`` offers these (``options_source``).
OPTIONS_SOURCE = "grunt.permissions"


@dataclass(frozen=True, slots=True)
class Perm:
    """A capability code checks. ``label`` is translatable (marked with ``N_``)."""

    name: str
    label: str
    description: str = ""
    app: str = "grunt"


_registry: dict[str, Perm] = {}


def register_perm(name: str, label: str, *, description: str = "", app: str = "grunt") -> Perm:
    """Declare permission *name* (``<app>.<verb>_<what>``)."""
    if not name or name == ALL or any(c.isspace() for c in name):
        raise ValueError(f"Invalid permission name {name!r}")
    perm = Perm(name, label, description, app)
    _registry[name] = perm
    return perm


def get_perm(name: str) -> Perm | None:
    return _registry.get(name)


def list_perms() -> list[Perm]:
    return list(_registry.values())


def _options() -> list[tuple[str, str]]:
    return [(ALL, _("Everything (*)"))] + [(p.name, _(p.label)) for p in _registry.values()]


register_option_provider(OPTIONS_SOURCE, _options)


# {site: {role: permissions}} - every Role of the site, loaded at once (roles are few).
_ROLE_PERMS: dict[str, dict[str, frozenset[str]]] = {}


@fanout
def invalidate_role_perms(site: str | None = None) -> None:
    """Drop the cached role permissions of *site* (``None`` - every site).
    Called from the Role controller after save / delete."""
    if site is None:
        _ROLE_PERMS.clear()
    else:
        _ROLE_PERMS.pop(site, None)


async def role_perms() -> dict[str, frozenset[str]]:
    """``{role: permissions}`` of the context's site."""
    key = site_cache_key()
    cached = _ROLE_PERMS.get(key)
    if cached is not None:
        return cached
    rows = await _db.get_all("Role", fields=["name", "permissions"], limit=None)
    loaded: dict[str, frozenset[str]] = {
        r["name"]: frozenset(r.get("permissions") or []) for r in rows
    }
    _ROLE_PERMS[key] = loaded
    return loaded


async def user_perms(user: str | None = None) -> frozenset[str]:
    """Every permission *user* (an email; ``None`` - the context's) holds through
    their roles - ``{"*"}`` stands for all of them."""
    if user is None:
        user = session_user()
    if not user:
        return frozenset()
    if user == SYSTEM_USER_EMAIL:
        return frozenset({ALL})
    if _session_ctx.get() is None:
        return frozenset()  # no database in context: nothing to load
    by_role = await role_perms()
    held: set[str] = set()
    for role in await get_roles(user):
        held |= by_role.get(role, frozenset())
    return frozenset(held)


async def has_perm(name: str, *, user: str | None = None) -> bool:
    """Whether *user* (an email; ``None`` - the context's) holds permission *name*."""
    if name not in _registry:
        raise KeyError(f"Unknown permission {name!r}: register it (hooks.py `permissions`)")
    held = await user_perms(user)
    return ALL in held or name in held


# The core's permissions.
for _name, _label in (
    ("grunt.manage_doctypes", N_("Manage document types")),
    ("grunt.manage_desk", N_("Manage workspaces and pages")),
    ("grunt.manage_users", N_("Manage users")),
    ("grunt.impersonate", N_("Sign in as another user")),
    ("grunt.manage_email", N_("Manage e-mail")),
    ("grunt.manage_storage", N_("Manage file storage")),
    ("grunt.manage_backups", N_("Manage backups")),
    ("grunt.manage_integrations", N_("Manage integrations (webhooks)")),
    ("grunt.manage_apps", N_("Manage apps and modules")),
    ("grunt.system_monitor", N_("System monitoring and background jobs")),
    ("grunt.moderate_comments", N_("Moderate comments")),
    ("grunt.restore_deleted", N_("Restore deleted documents")),
    ("grunt.bulk_delete", N_("Fast bulk delete")),
):
    register_perm(_name, _label)
