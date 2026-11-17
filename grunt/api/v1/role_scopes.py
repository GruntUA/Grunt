"""What the current user's role scopes mean for the desk UI: the list's
"Restrictions" popup and the Link fields a new form starts with
(:func:`grunt.permissions.scopes.scoped_values`)."""

from typing import Any

from grunt.api.context import whitelist
from grunt.document.titles import resolve_reference_titles
from grunt.errors import not_found
from grunt.i18n import _
from grunt.local import session_user
from grunt.metadata.registry import doctype_registry
from grunt.permissions.roles import role_access
from grunt.permissions.scopes import scoped_values


@whitelist()
async def get_active_scopes(doctype: str) -> list[dict[str, Any]]:
    """What the current user's role scopes limit a *doctype* list to - for the
    list's "Restrictions" popup: ``[{field, fieldname, allow, value, title}]``."""
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    access = await role_access(dt, session_user())
    scoped = scoped_values(access, "read")
    if not scoped:
        return []
    titles = await resolve_reference_titles(
        [(scope_doctype, v) for scope_doctype, values in scoped.items() for v in values]
    )
    out: list[dict[str, Any]] = []
    for scope_doctype, values in sorted(scoped.items()):
        for fieldname in access.scope_fields(scope_doctype):
            label = "ID" if fieldname == "name" else dt.get_label(fieldname)
            for value in sorted(values):
                out.append(
                    {
                        "field": label,
                        "fieldname": fieldname,
                        "allow": scope_doctype,
                        "value": value,
                        "title": titles.get((scope_doctype, value), value),
                    }
                )
    return out


@whitelist()
async def get_scope_defaults(doctype: str) -> dict[str, str]:
    """``{fieldname: value}`` to pre-fill on a new *doctype* form: a user who may
    create it only within one record of a scope DocType gets that record in
    its Link fields."""
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    access = await role_access(dt, session_user())
    defaults: dict[str, str] = {}
    for scope_doctype, values in (scoped_values(access, "create") or {}).items():
        if len(values) != 1:
            continue
        (value,) = values
        for fieldname in access.scope_fields(scope_doctype):
            if fieldname != "name":
                defaults.setdefault(fieldname, value)
    return defaults
