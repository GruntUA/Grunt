"""The access inspector: why a user may (or may not) do something with a
DocType or one document - :func:`grunt.permissions.explain.explain` for the
desk ("Check access" on a form or a list)."""

from typing import Any

from grunt.api.context import whitelist
from grunt.db.api import GruntDB
from grunt.document.titles import resolve_reference_titles
from grunt.errors import not_found, throw
from grunt.i18n import _
from grunt.metadata.permission import ACTIONS
from grunt.metadata.registry import doctype_registry
from grunt.permissions.explain import explain
lazy from grunt.store.lookup import store_for

_db = GruntDB()  # stateless: reads through the context's session


@whitelist(perm="grunt.manage_permissions")
async def explain_access(
    user: str, doctype: str, action: str = "read", name: str | None = None
) -> dict[str, Any]:
    """Whether *user* (an email or a User id) may perform *action* on *doctype*
    - or on its document *name* - and the rules, shares and followed documents
    behind the answer."""
    if action not in ACTIONS:
        throw(_("Unknown action “%(action)s”") % {"action": action}, "VALIDATION_ERROR")
    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    found = await _db.get_value("User", {"email": user}, ["email", "full_name"], as_dict=True)
    found = found or await _db.get_value("User", user, ["email", "full_name"], as_dict=True)
    if not found:
        raise not_found(_("User “%(user)s” not found") % {"user": user})
    doc = None
    if name:
        lookup = meta.name if meta.is_singleton else name
        doc = await store_for(meta).get(lookup, expand=[])
        if doc is None:
            raise not_found(_("Document not found"))
    trace = await explain(found["email"], meta, action, doc)  # type: ignore[arg-type]
    trace["user_name"] = found.get("full_name") or found["email"]
    trace["titles"] = await _scope_titles(trace)
    return trace


async def _scope_titles(trace: dict[str, Any]) -> dict[str, str]:
    """``"<DocType>/<id>" -> title`` of every scope record the trace names."""
    refs = {
        (row["scope_doctype"], row["scope_value"])
        for row in trace["roles"]
        if row.get("scope_doctype") and row.get("scope_value")
    }
    refs |= {
        (scope["doctype"], value)
        for rule in trace["rules"]
        for scope in rule["scopes"]
        for value in scope["values"]
    }
    titles = await resolve_reference_titles(sorted(refs))
    return {f"{doctype}/{value}": title for (doctype, value), title in titles.items()}
