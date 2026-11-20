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
from grunt.db.api import GruntDB
from grunt.i18n import N_, _
from grunt.local import _session_ctx, session_user
from grunt.metadata.dynamic_options import register_option_provider
from grunt.permissions.role_props import role_props
from grunt.permissions.roles import BUILT_IN_ROLES, get_roles

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


async def role_perms() -> dict[str, frozenset[str]]:
    """``{role: permissions}`` of the context's site - a disabled role grants none."""
    return {
        name: frozenset() if props.disabled else props.permissions
        for name, props in (await role_props()).items()
    }


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


@dataclass(frozen=True)
class Landing:
    """Where a user works: ``site_only`` - on the website, without the
    workspace (``/app``); ``home_page`` - where they land after signing in."""

    site_only: bool
    home_page: str | None


async def user_landing(user: str | None = None) -> Landing:
    """:class:`Landing` of *user* (an email; ``None`` - the context's), from
    their roles in the order they're assigned. Site-only only when they hold
    roles and every one of them is site-only - a user without roles keeps the
    workspace; whoever holds every permission (``*``) always does."""
    if _session_ctx.get() is None:
        return Landing(site_only=False, home_page=None)  # no database in context
    props = await role_props()
    held = [props[r] for r in await get_roles(user) if r in props and r not in BUILT_IN_ROLES]
    home = next((p.home_page for p in held if p.home_page), None)
    site_only = bool(held) and all(p.site_only for p in held)
    if site_only and ALL in await user_perms(user):
        site_only = False
    return Landing(site_only=site_only, home_page=home)


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
    ("grunt.manage_permissions", N_("Inspect and manage access rights")),
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
