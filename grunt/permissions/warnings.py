"""Access settings that probably don't do what was meant (PERMISSIONS_PLAN step 6d).

Shown on the DocType and Role forms - nothing here blocks a save:

* a DocType without a single rule (nobody but system tasks reaches it);
* a rule that grants no action;
* rules for roles nobody holds (one warning listing them);
* a field hidden from everyone who may read the DocType, or read-only for
  everyone who may change it;
* a role nobody holds; a role with no rule and no permission (it works only
  where code checks it by name - ``@whitelist(roles=...)``).

``All`` and ``Guest`` are principals, not assignments - never "without users".
"""

from typing import Any

from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry
from grunt.permissions.roles import BUILT_IN_ROLES, role_holders

_db = GruntDB()  # stateless: reads through the context's session


async def doctype_warnings(doctype: Any) -> list[dict[str, str]]:
    """Warnings for a DocType (``DocType`` / ``Meta``): ``[{code, message}]``."""
    meta = getattr(doctype, "doc", doctype)
    if getattr(meta, "is_child", False):
        return []  # child rows follow their parent - no rules of their own
    rules = list(getattr(meta, "permissions", None) or [])
    if not rules:
        return [
            _warn(
                "no_rules",
                _("No rule grants anything here: only system tasks can reach these documents."),
            )
        ]
    out: list[dict[str, str]] = []
    for rule in rules:
        if not rule.actions:
            out.append(
                _warn(
                    "rule_grants_nothing",
                    _("The rule for “%(role)s” grants no action.") % {"role": rule.role},
                )
            )
    roles = sorted({r.role for r in rules if r.role not in BUILT_IN_ROLES})
    held = await _held_roles(roles)
    unheld = [role for role in roles if role not in held]
    if unheld:
        out.append(
            _warn(
                "role_without_users",
                _("Nobody holds these roles - their rules give access to no one: %(roles)s")
                % {"roles": ", ".join(unheld)},
            )
        )
    out += _fields_nobody_gets(meta, rules, "read", "hidden_fields")
    out += _fields_nobody_gets(meta, rules, "write", "readonly_fields")
    return out


async def role_warnings(role: str) -> list[dict[str, str]]:
    """Warnings for a Role: nobody holds it; it grants nothing."""
    if role in BUILT_IN_ROLES or role == "System Manager":
        return []
    out: list[dict[str, str]] = []
    if role not in await _held_roles([role]):
        out.append(_warn("role_without_users", _("Nobody holds this role.")))
    granting = [
        dt.name
        for dt in await doctype_registry.list_all()
        if any(r.role == role and r.actions for r in dt.permissions)
    ]
    permissions = await _role_permissions(role)
    if not granting and not permissions:
        out.append(
            _warn(
                "role_grants_nothing",
                _(
                    "No document type has a rule for this role and it holds no permission - "
                    "it works only where code checks the role by name."
                ),
            )
        )
    return out


def _fields_nobody_gets(
    meta: Any, rules: list[Any], action: str, attr: str
) -> list[dict[str, str]]:
    """Fields every rule granting *action* lists in *attr* - hidden from (or
    read-only for) everyone who may read (change) the documents."""
    granting = [r for r in rules if r.grants(action)]
    if not granting:
        return []
    common = set.intersection(*(set(getattr(r, attr, None) or []) for r in granting))
    labels = {f.fieldname: f.label or f.fieldname for f in meta.fields}
    message = (
        _("The field “%(field)s” is hidden from everyone who may read these documents.")
        if action == "read"
        else _("The field “%(field)s” is read-only for everyone who may change these documents.")
    )
    code = "field_hidden_from_all" if action == "read" else "field_readonly_for_all"
    return [_warn(code, message % {"field": _(labels.get(name, name))}) for name in sorted(common)]


async def _held_roles(roles: list[str]) -> set[str]:
    """Those of *roles* at least one active user holds today."""
    if not roles:
        return set()
    return {role for holder in await role_holders(roles) for role in holder["roles"]}


async def _role_permissions(role: str) -> list[str]:
    found = await _db.get_value("Role", {"role_name": role}, "permissions")
    return list(found or [])


def _warn(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}
