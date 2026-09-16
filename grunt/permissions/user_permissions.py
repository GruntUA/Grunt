"""User Permissions — per-user, record-level access restrictions.

A ``UserPermission`` row {user, allow, for_value} means *user* may only see /
touch documents that link (via a Link field) to *for_value* of DocType *allow*.

* Multiple rows with the same ``allow`` widen the allowed set (OR).
* Different ``allow`` types narrow it (AND).
* ``apply_to_all_doctypes`` — the rule binds every DocType with a Link to
  ``allow``; otherwise only ``applicable_for``.
* A Link field flagged ``ignore_user_permissions`` is skipped when matching —
  lets a DocType keep a free-reference Link to ``allow`` alongside the one
  that actually scopes access.
* ``is_default`` — ``for_value`` pre-fills the matching Link field on new docs.
* When ``allow`` is a tree DocType, ``for_value`` also authorises the whole
  subtree beneath it (a parent department → all its sub-units).

Not applied to System Manager. When SystemSettings
``apply_strict_user_permissions`` is on, a restricted ``allow`` with no Link
field on the target DocType (or a NULL value) blocks rather than passes.

Wired into ``apply_permission_filter`` (lists / counts / link search / reports)
and ``PermissionChecker.check`` (single-document read / write / delete).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, false, or_

import grunt

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.sql import ColumnElement

    from grunt.auth.doctypes.User.user import User
    from grunt.document.meta import Meta
    from grunt.metadata.doctype import DocType


# {user_email: {allow_doctype: {scope: set(for_value)}}}  scope = "*" | applicable_for
_UP_CACHE: dict[str, dict[str, dict[str, set[str]]]] = {}


def invalidate_user_permission_cache(user_id: str | None = None) -> None:
    """Drop cached rows for one user (or all). Called from the UserPermission
    controller's after_save / after_delete."""
    if user_id is None:
        _UP_CACHE.clear()
    else:
        _UP_CACHE.pop(user_id, None)


def user_permissions_apply_to(user: User | None) -> bool:
    """User Permissions bind everyone except System Manager."""
    if user is None:
        return False
    return "System Manager" not in (getattr(user, "roles", None) or [])


async def _strict_mode() -> bool:
    from grunt.site.settings import get_setting

    return bool(await get_setting("apply_strict_user_permissions", False))


async def _load(user_email: str) -> dict[str, dict[str, set[str]]]:
    from grunt.app import grunt

    rows = await grunt.db.get_all(
        "UserPermission",
        filters={"for_user": user_email},
        fields=["allow", "for_value", "apply_to_all_doctypes", "applicable_for"],
        limit=5000,
    )
    out: dict[str, dict[str, set[str]]] = {}
    for r in rows:
        scope = "*" if r.get("apply_to_all_doctypes") else (r.get("applicable_for") or "*")
        out.setdefault(r["allow"], {}).setdefault(scope, set()).add(r["for_value"])
    return out


async def get_user_permissions_for(user: User | None, doctype_name: str) -> dict[str, set[str]]:
    """``{allow_doctype: {allowed for_values}}`` that constrain *doctype_name*.

    Empty when the user is exempt or has no relevant rows.
    """
    if not user_permissions_apply_to(user):
        return {}
    email = getattr(user, "email", None) or getattr(user, "id", None)
    if not email:
        return {}

    by_allow = _UP_CACHE.get(email)
    if by_allow is None:
        try:
            by_allow = await _load(email)
        except RuntimeError:
            # No active DB session (e.g. a bare permission_checker unit test) —
            # there's nothing to load, so impose no restriction.
            return {}
        _UP_CACHE[email] = by_allow

    result: dict[str, set[str]] = {}
    for allow, by_scope in by_allow.items():
        vals = by_scope.get("*", set()) | by_scope.get(doctype_name, set())
        if vals:
            result[allow] = vals
    return result


async def _expand_tree_values(allow: str, values: set[str]) -> set[str]:
    """When *allow* is a tree DocType, widen *values* to every descendant so a
    UserPermission on a parent node authorises its whole subtree (an
    institution → all its sub-departments).

    Non-tree ``allow`` — the common case — returns *values* unchanged after a
    single in-memory registry hit. Tree ``allow`` costs a couple of small
    indexed queries per list render; departments/units are few enough that
    caching isn't worth the staleness risk.
    """
    from grunt.app import grunt

    dt = await grunt.get_meta(allow)
    if dt is None:
        return values
    parent_field = getattr(dt, "tree_parent_field", None)
    if not getattr(dt, "is_tree", False) or not parent_field:
        return values

    out = set(values)
    frontier = list(values)
    while frontier:
        rows = await grunt.db.get_all(
            allow,
            filters={f"{parent_field}__in": frontier},
            fields=["name"],
            limit=10000,
        )
        children = [r["name"] for r in rows if r["name"] not in out]
        out.update(children)
        frontier = children
    return out


def _link_fieldnames(doctype: DocType | Meta, allow: str) -> list[str]:
    """Fields on *doctype* that Link to *allow* (plus ``name`` when the DocType
    is itself restricted). DynamicLink fields are skipped — their target isn't
    statically known."""
    names: list[str] = []
    if allow == doctype.name:
        names.append("name")
    names.extend(
        f.fieldname
        for f in doctype.fields
        if f.fieldtype == "Link"
        and f.options == allow
        and not getattr(f, "ignore_user_permissions", False)
    )
    return names


async def build_conditions(
    table: Table,
    user: User | None,
    doctype: DocType | Meta,
) -> list[ColumnElement] | None:
    """SQL conditions (AND-joined by the caller) enforcing *user*'s permissions
    on *doctype*, or ``None`` when nothing applies. May return ``[false()]`` to
    deny every row (strict mode, restricted type with no link field)."""
    up = await get_user_permissions_for(user, doctype.name)
    if not up:
        return None

    strict = await _strict_mode()
    conds: list[ColumnElement] = []
    for allow, values in up.items():
        values = await _expand_tree_values(allow, values)
        fields = [fn for fn in _link_fieldnames(doctype, allow) if fn in table.c]
        if not fields:
            if strict:
                return [false()]
            continue
        per_field: list[ColumnElement] = []
        for fn in fields:
            col = table.c[fn]
            cond = col.in_(values)
            if not strict:
                cond = or_(cond, col.is_(None))
            per_field.append(cond)
        conds.append(and_(*per_field))
    return conds or None


async def doc_passes(user: User | None, doctype: DocType | Meta, doc: dict[str, Any]) -> bool:
    """Python-level check of a single already-fetched *doc* against *user*'s
    permissions — the per-document counterpart of :func:`build_conditions`."""
    up = await get_user_permissions_for(user, doctype.name)
    if not up:
        return True

    strict = await _strict_mode()
    for allow, values in up.items():
        values = await _expand_tree_values(allow, values)
        fields = _link_fieldnames(doctype, allow)
        checkable = [fn for fn in fields if fn == "name" or fn in doc]
        if not checkable:
            if strict:
                return False
            continue
        for fn in checkable:
            value = doc.get("name") if fn == "name" else doc.get(fn)
            if value in (None, ""):
                if strict:
                    return False
                continue
            if value not in values:
                return False
    return True


# ── Whitelisted endpoints ────────────────────────────────────────────────


@grunt.whitelist()
async def get_active_restrictions(doctype: str) -> list[dict[str, Any]]:
    """Rows for the list-view "Restrictions" popup: which fields on *doctype*
    are constrained, and to which values, for the current user."""
    from grunt.app import grunt as grunt_app
    from grunt.errors import not_found

    user = await grunt.get_current_user()
    dt = await grunt_app.get_meta(doctype)
    if dt is None:
        raise not_found(f"DocType «{doctype}» не знайдено")
    up = await get_user_permissions_for(user, doctype)
    if not up:
        return []

    out: list[dict[str, Any]] = []
    for allow, values in up.items():
        for fn in _link_fieldnames(dt, allow):
            label = "ID" if fn == "name" else dt.get_label(fn)
            for value in sorted(values):
                out.append({"field": label, "fieldname": fn, "allow": allow, "value": value})
    return out


@grunt.whitelist()
async def get_user_permission_defaults(doctype: str) -> dict[str, str]:
    """``{fieldname: value}`` to pre-fill on a new *doctype* form from the
    current user's ``is_default`` UserPermission rows."""
    from grunt.app import grunt as grunt_app
    from grunt.errors import not_found

    user = await grunt.get_current_user()
    if not user_permissions_apply_to(user):
        return {}
    email = getattr(user, "email", None)
    if not email:
        return {}

    rows = await grunt.db.get_all(
        "UserPermission",
        filters={"for_user": email, "is_default": True},
        fields=["allow", "for_value", "apply_to_all_doctypes", "applicable_for"],
        limit=500,
    )
    if not rows:
        return {}

    dt = await grunt_app.get_meta(doctype)
    if dt is None:
        raise not_found(f"DocType «{doctype}» не знайдено")
    defaults: dict[str, str] = {}
    for r in rows:
        if not r.get("apply_to_all_doctypes") and r.get("applicable_for") != doctype:
            continue
        for fn in _link_fieldnames(dt, r["allow"]):
            if fn != "name":
                defaults.setdefault(fn, r["for_value"])
    return defaults
