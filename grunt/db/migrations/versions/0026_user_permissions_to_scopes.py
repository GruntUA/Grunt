"""User Permissions become scoped roles (PERMISSIONS_PLAN step 4b).

A ``UserPermission`` (user, ``allow`` DocType, value, for one DocType or all)
narrowed every grant path of the user - all roles, ``All`` rules, shares; a
scoped role assignment (a ``UserRole`` row with ``scope_doctype`` /
``scope_value``) narrows only its own role, on every DocType that is, or links
to, the scope DocType. The migration moves only what a scope says **exactly**,
and never widens access:

* A user holding a role with every permission (``*``) is left alone: User
  Permissions didn't bind them.
* A role of the user is converted when, for each ``allow`` it meets (a DocType
  it has a rule on is, or links to, ``allow`` - through a Link field, not one
  flagged ``ignore_user_permissions``), every such DocType was restricted to
  the same values: the scope is then exactly that restriction. A DocType the
  role reaches that wasn't restricted, or was with other values, leaves the
  role as it is (a scope would narrow or widen it).
* A User Permission is deleted only when every grant path on the DocTypes it
  restricted is now scoped instead - each role of the user with a rule there
  converted, no ``All`` rule there, nothing shared with the user there.
  Otherwise it stays, still narrowing everything, and is logged: step 4c
  (removing ``UserPermission``) decides those.

The scope columns are added when the DocType sync hasn't run yet.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-16
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0026")

_UP = "grunt_permissions_user_permission"
_ROLES = "grunt_auth_user_role"
_ROLE = "grunt_auth_role"
_META = "grunt_metadata_doc_type"
_SHARED = "grunt_permissions_shared_with"
_SCOPE_COLUMNS = {
    "scope_doctype": sa.Text(),
    "scope_value": sa.Text(),
    "valid_from": sa.Date(),
    "valid_to": sa.Date(),
}


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _definitions(conn: sa.Connection) -> dict[str, dict]:
    meta = sa.table(_META, sa.column("name"), sa.column("definition"))
    return {
        name: _json(d) or {} for name, d in conn.execute(sa.select(meta.c.name, meta.c.definition))
    }


def _links_to(definition: dict, name: str, allow: str) -> bool:
    """Whether DocType *name* is, or links to, *allow* the way a scope applies:
    through a Link field (as the runtime's ``link`` trait), not one flagged
    ``ignore_user_permissions``."""
    if name == allow:
        return True
    return any(
        f.get("fieldtype") == "Link"
        and f.get("options") == allow
        and not f.get("ignore_user_permissions")
        for f in definition.get("fields") or []
    )


def _restricted(user_ups: list[dict], doctype: str, allow: str) -> frozenset[str]:
    """Values *doctype* was restricted to by the user's User Permissions on *allow*."""
    return frozenset(
        up["for_value"]
        for up in user_ups
        if up["allow"] == allow and (up["apply_to_all_doctypes"] or up["applicable_for"] == doctype)
    )


def _role_scopes(
    role: str,
    user_ups: list[dict],
    ruled: dict[str, set[str]],
    definitions: dict[str, dict],
) -> dict[str, frozenset[str]] | None:
    """``{allow: values}`` that say exactly what User Permissions did to *role*,
    or ``None`` when no scope can (or there is nothing to say)."""
    scopes: dict[str, frozenset[str]] = {}
    for allow in sorted({up["allow"] for up in user_ups}):
        reached = [dt for dt in ruled[role] if _links_to(definitions.get(dt) or {}, dt, allow)]
        if not reached:
            continue
        values = {_restricted(user_ups, dt, allow) for dt in reached}
        if len(values) != 1 or not next(iter(values)):
            return None  # restricted differently, or not at all, across the role's DocTypes
        scopes[allow] = next(iter(values))
    return scopes or None


def _shared_doctypes(conn: sa.Connection, tables: set[str], user: str) -> set[str]:
    if _SHARED not in tables:
        return set()
    shared = sa.table(_SHARED, sa.column("reference_doctype"), sa.column("user"))
    query = sa.select(shared.c.reference_doctype).where(shared.c.user == user).distinct()
    return {r[0] for r in conn.execute(query)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if _UP not in tables or _ROLES not in tables:
        return
    ups = sa.table(
        _UP,
        sa.column("name"),
        sa.column("for_user"),
        sa.column("allow"),
        sa.column("for_value"),
        sa.column("apply_to_all_doctypes"),
        sa.column("applicable_for"),
    )
    rows = conn.execute(sa.select(ups)).mappings().all()
    if not rows:
        return

    columns = {c["name"] for c in sa.inspect(conn).get_columns(_ROLES)}
    for column, type_ in _SCOPE_COLUMNS.items():
        if column not in columns:
            op.add_column(_ROLES, sa.Column(column, type_))
    roles_t = sa.table(
        _ROLES,
        *(
            sa.column(c)
            for c in (
                "name",
                "owner",
                "created_at",
                "modified_at",
                "modified_by",
                "role_name",
                "parent_name",
                "parent_doctype",
                "parent_field",
                "idx",
                *_SCOPE_COLUMNS,
            )
        ),
    )

    definitions = _definitions(conn)
    # Role -> DocTypes it has a rule on.
    ruled: dict[str, set[str]] = defaultdict(set)
    for name, definition in definitions.items():
        for perm in definition.get("permissions") or []:
            if isinstance(perm, dict) and perm.get("role"):
                ruled[perm["role"]].add(name)
    everything: set[str] = set()
    if _ROLE in tables:
        role_t = sa.table(_ROLE, sa.column("name"), sa.column("permissions"))
        for name, perms in conn.execute(sa.select(role_t.c.name, role_t.c.permissions)):
            if "*" in (_json(perms) or []):
                everything.add(name)

    by_user: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_user[row["for_user"]].append(dict(row))

    now = datetime.now(UTC)
    for user, user_ups in by_user.items():
        assigned = (
            conn.execute(
                sa.select(roles_t).where(
                    roles_t.c.parent_name == user, roles_t.c.parent_doctype == "User"
                )
            )
            .mappings()
            .all()
        )
        held = {a["role_name"] for a in assigned}
        if held & everything:
            log.warning("0026: %s holds every permission (*) - User Permissions kept", user)
            continue

        converted: set[str] = set()
        next_idx = max((a["idx"] or 0 for a in assigned), default=0)
        for assignment in assigned:
            role = assignment["role_name"]
            if assignment["scope_doctype"] or role in converted:
                continue
            if any(a["role_name"] == role and a["scope_doctype"] for a in assigned):
                continue  # already scoped elsewhere - not ours to merge
            scopes = _role_scopes(role, user_ups, ruled, definitions)
            if scopes is None:
                continue
            for other in [a for a in assigned if a["role_name"] == role]:
                conn.execute(roles_t.delete().where(roles_t.c.name == other["name"]))
            for allow, values in sorted(scopes.items()):
                for value in sorted(values):
                    next_idx += 1
                    conn.execute(
                        roles_t.insert().values(
                            name=uuid.uuid4().hex[:10],
                            owner="system",
                            created_at=now,
                            modified_at=now,
                            modified_by="system",
                            role_name=role,
                            parent_name=user,
                            parent_doctype="User",
                            parent_field=assignment["parent_field"] or "roles",
                            idx=next_idx,
                            scope_doctype=allow,
                            scope_value=value,
                            valid_from=assignment.get("valid_from"),
                            valid_to=assignment.get("valid_to"),
                        )
                    )
            converted.add(role)
            log.info(
                "0026: %s - role %r scoped to %s",
                user,
                role,
                {k: sorted(v) for k, v in scopes.items()},
            )

        shared = _shared_doctypes(conn, tables, user)
        drop: list[str] = []
        for up in user_ups:
            restricted = (
                [dt for dt, d in definitions.items() if _links_to(d, dt, up["allow"])]
                if up["apply_to_all_doctypes"]
                else [up["applicable_for"]]
            )
            open_paths = sorted(
                f"{dt}: {path}"
                for dt in restricted
                for path in (
                    *(r for r in held - converted if dt in ruled[r]),
                    *(["All"] if dt in ruled["All"] else []),
                    *(["shared"] if dt in shared else []),
                )
            )
            if open_paths:
                log.warning(
                    "0026: %s - UserPermission %s=%s (%s) kept, still narrows %s",
                    user,
                    up["allow"],
                    up["for_value"],
                    up["applicable_for"] or "all DocTypes",
                    ", ".join(open_paths),
                )
            else:
                drop.append(up["name"])
        if drop:
            conn.execute(ups.delete().where(ups.c.name.in_(drop)))


def downgrade() -> None:
    pass
