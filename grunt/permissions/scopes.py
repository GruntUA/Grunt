"""Scoped roles - a role assignment limited to documents linked to one record.

A ``UserRole`` row may carry a scope (``scope_doctype`` + ``scope_value``): the
role then holds only for documents that link to that record - a department and,
for a tree DocType, every unit below it. The scope narrows **the rules of that
role only** (ANDed to their ``match``); shares and rules of the user's other
roles are untouched.

* An assignment without a scope makes the role hold everywhere - its scoped
  assignments narrow nothing then.
* Scopes of one DocType widen each other (OR); scopes of different DocTypes
  narrow each other (AND).
* A DocType that neither is the scope DocType nor links to it isn't narrowed
  by that scope.
* Several Link fields to the scope DocType: every filled one must be in scope,
  and at least one must be filled - a document linking to nothing lies outside
  every scope (fail closed).

Lists and single documents share the expression (:func:`scope_predicate`,
called from ``grunt.permissions.query``), so a document opens exactly when a
list would hold it - for the new values of a write too.
"""

from collections.abc import Collection, Mapping
from typing import Any

from grunt.metadata.permission import DocPermission
from grunt.permissions.access import RoleAccess, Scope
from grunt.permissions.roles import role_holders
from grunt.permissions.trees import expand_tree_values
from grunt.query.evaluate import matches
from grunt.query.nodes import FALSE, Empty, Expr, In, and_, or_


async def scope_predicate(
    access: RoleAccess, perm: DocPermission, columns: Collection[str]
) -> Expr | None:
    """The rows *perm* is narrowed to by its role's scopes - ``None`` when it
    isn't narrowed on this DocType."""
    bound = access.bound_scopes(perm)
    if not bound:
        return None
    conditions: list[Expr] = []
    for scope_doctype, values in sorted(bound.items()):
        fields = [f for f in access.scope_fields(scope_doctype) if f in columns]
        if not fields:
            return FALSE  # links to the scope, but not as a stored column
        allowed = tuple(sorted(await expand_tree_values(scope_doctype, set(values))))
        conditions.append(_in_scope(fields, allowed))
    return and_(*conditions)


def _in_scope(fields: list[str], allowed: tuple[str, ...]) -> Expr:
    if len(fields) == 1:
        return In(fields[0], allowed)  # NULL is not in it
    filled = or_(*(Empty(f, negate=True) for f in fields))
    return and_(filled, *(or_(In(f, allowed), Empty(f)) for f in fields))


async def doc_in_scopes(
    access: RoleAccess, scopes: Collection[Scope], doc: Mapping[str, Any]
) -> bool:
    """Whether *doc* (of ``access.doctype``) lies within *scopes* - the
    per-document question for "who holds this role for this document"
    (notification recipients, workflow actors). No scope binding the DocType
    - yes."""
    bound: dict[str, set[str]] = {}
    for scope_doctype, value in scopes:
        if access.scope_fields(scope_doctype):
            bound.setdefault(scope_doctype, set()).add(value)
    for scope_doctype, values in bound.items():
        fields = access.scope_fields(scope_doctype)
        allowed = tuple(await expand_tree_values(scope_doctype, values))
        if not matches(_in_scope(fields, allowed), dict(doc)):
            return False
    return True


async def holders_for(
    roles: Collection[str], doctype: Any | None = None, doc: Mapping[str, Any] | None = None
) -> list[str]:
    """Emails of active users holding one of *roles* today - with *doctype*
    (a ``DocType``/``Meta``) and *doc*, only those whose assignment's scope
    covers that document."""
    out: list[str] = []
    for holder in await role_holders(roles):
        email = holder.get("email")
        if not email:
            continue
        if (
            doctype is not None
            and doc is not None
            and not await _covers(RoleAccess(doctype, email, []), holder["roles"].values(), doc)
        ):
            continue
        out.append(email)
    return out


async def _covers(
    access: RoleAccess, held: Collection[frozenset[Scope]], doc: Mapping[str, Any]
) -> bool:
    """One of the held roles (each - its scopes, empty: everywhere) covers *doc*."""
    for scopes in held:
        if not scopes or await doc_in_scopes(access, scopes, doc):
            return True
    return False


def scoped_values(access: RoleAccess, action: str) -> dict[str, set[str]] | None:
    """``{scope DocType: values}`` the user's rules granting *action* are held
    within - ``None`` when one of those rules holds everywhere (nothing to
    narrow) or none grants it. Rules of several scopes add up."""
    granting = [p for p in access.matching_permissions() if p.grants(action)]
    if access.is_unrestricted or not granting:
        return None
    out: dict[str, set[str]] = {}
    for perm in granting:
        bound = access.bound_scopes(perm)
        if not bound:
            return None
        for scope_doctype, values in bound.items():
            out.setdefault(scope_doctype, set()).update(values)
    return out
