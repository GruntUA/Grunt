"""Why a user may (or may not) do something - the trace behind one access
decision, for the access inspector (PERMISSIONS_PLAN step 6a).

The verdict is always :meth:`PermissionChecker.check` itself; the trace lists
the facts it is made of, each evaluated the way the predicate evaluates it:

* the user's role assignments in force (with scope and end date);
* every rule of the DocType - whether the user holds its role, whether it
  grants the action and, for a document, whether its ``match`` and its role's
  scope let this document through;
* shares of the document that reach the user and grant the action;
* for reading: the documents access follows (``access_from``, a child row's
  parent) and whether the user may read them - a document that points at one
  follows its access instead of the rules' ``match`` (the user still needs a
  rule granting the action at all);
* fields hidden from the user / read-only for them.
"""

from typing import Any

from grunt.document.meta import Meta
from grunt.metadata.permission import DocPermission
from grunt.metadata.registry import doctype_registry
from grunt.permissions import query, shares
from grunt.permissions.access import RoleAccess
from grunt.permissions.match import PermissionMatch
from grunt.permissions.rbac import permission_checker
from grunt.permissions.roles import get_role_rows, role_access
from grunt.permissions.scopes import scope_predicate
from grunt.permissions.types import PermissionAction
from grunt.query.evaluate import matches_linked
from grunt.query.nodes import TRUE, Cmp, Expr, and_
from grunt.query.query import Query
lazy from grunt.store.lookup import store_for


async def explain(
    user: str, meta: Meta, action: PermissionAction, doc: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The decision on *action* by *user* on *meta*'s DocType (and *doc*) with
    the facts behind it - see the module doc."""
    access = await role_access(meta, user)
    trace: dict[str, Any] = {
        "user": user,
        "doctype": meta.name,
        "action": action,
        "doc": str(doc.get("name")) if doc else None,
        "allowed": await permission_checker.check(meta, action, doc, user=user),
        "roles": [
            {
                "role": row["role_name"],
                "scope_doctype": row.get("scope_doctype") or None,
                "scope_value": row.get("scope_value") or None,
                "valid_to": _iso(row.get("valid_to")),
            }
            for row in await get_role_rows(user)
        ],
        "child": query.is_child(meta),
        "rules": [],
        # A role rule grants the action at all (whatever its match / scope).
        "role_grants": any(p.grants(action) for p in access.matching_permissions()),
        # The rules' match and scope decide - False: the document follows the
        # access of the documents it points at (``followed``).
        "rules_decide": True,
        "shares": [],
        "followed": [],
        "hidden_fields": sorted(access.hidden_fields),
        "readonly_fields": sorted(access.readonly_fields),
    }
    if query.is_child(meta):
        # A child row has no rules of its own: it follows its parent.
        if doc is not None and action in query.READ_ACTIONS:
            trace["followed"] = await _followed_docs(user, meta, doc, [query.CHILD_SOURCE])
        return trace
    if doc is not None and action in query.READ_ACTIONS:
        trace["followed"] = await _followed_docs(user, meta, doc, query.access_sources(meta))
        trace["rules_decide"] = not trace["followed"]
    decide = doc is not None and trace["rules_decide"]
    trace["rules"] = [
        await _rule(access, meta, perm, index, action, doc if decide else None)
        for index, perm in enumerate(meta.permissions)
    ]
    if doc is not None:
        trace["shares"] = await _shares(user, meta, action, doc)
    return trace


async def _rule(
    access: RoleAccess,
    meta: Meta,
    perm: DocPermission,
    index: int,
    action: str,
    doc: dict[str, Any] | None,
) -> dict[str, Any]:
    held = perm.role == "All" or perm.role in access.user_roles
    out: dict[str, Any] = {
        "index": index,
        "role": perm.role,
        "held": held,
        "grants": perm.grants(action),
        "match": perm.match or None,
        "scopes": [],
        "unparseable": False,
        "doc_ok": None,
    }
    if not held:
        return out
    out["scopes"] = [
        {"doctype": scope_doctype, "values": sorted(values)}
        for scope_doctype, values in sorted(access.bound_scopes(perm).items())
    ]
    if doc is None or not out["grants"]:
        return out
    columns = meta.columns
    condition: Expr = TRUE
    if perm.match:
        parsed = await PermissionMatch(perm.match).to_expr(columns, access.user, meta)
        if parsed is None:
            out["unparseable"] = True
            out["doc_ok"] = False
            return out
        condition = parsed
    scope = await scope_predicate(access, perm, columns)
    if scope is not None:
        condition = and_(condition, scope)
    out["doc_ok"] = await matches_linked(condition, dict(doc), query.linked_exists)
    return out


async def _shares(user: str, meta: Meta, action: str, doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The shares of *doc* that reach *user* and grant *action* today."""
    shared = await doctype_registry.get_meta("SharedWith")
    if shared is None or action not in shares.SHAREABLE_ACTIONS or not doc.get("name"):
        return []
    where = and_(
        await shares.grants(user, meta.name, action),
        Cmp("reference_id", "eq", str(doc["name"])),
    )
    rows = await store_for(shared).fetch(Query(doctype=shared.name, where=where))
    return [
        {
            "name": str(row["name"]),
            "via": "user" if row.get("user") else "role" if row.get("role") else "everyone",
            "role": row.get("role") or None,
            "permission": row.get("permission"),
            "can_reshare": bool(row.get("can_reshare")),
            "valid_to": _iso(row.get("valid_to")),
        }
        for row in rows
    ]


async def _followed_docs(
    user: str, meta: Meta, doc: dict[str, Any], sources: list[query.Source]
) -> list[dict[str, Any]]:
    """The documents *doc* points at through *sources* and whether *user* may
    read each - the access a comment, file or child row follows."""
    out: list[dict[str, Any]] = []
    for dt_field, id_field in sources:
        ref_id = doc.get(id_field)
        ref_doctype = doc.get(dt_field) if dt_field else query.link_target(meta, id_field)
        if not ref_id or not ref_doctype:
            continue
        target = await doctype_registry.get_meta(str(ref_doctype))
        if target is None:
            continue
        lookup = target.name if target.is_singleton else str(ref_id)
        parent = await store_for(target).get(lookup, expand=[])
        allowed = parent is not None and await permission_checker.check(
            target, "read", parent, user=user
        )
        out.append(
            {"field": id_field, "doctype": target.name, "name": str(ref_id), "allowed": allowed}
        )
    return out


def _iso(value: Any) -> str | None:
    return str(value)[:10] if value else None
