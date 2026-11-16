"""User Permissions become scoped roles (PERMISSIONS_PLAN step 4b).

A ``UserPermission`` (user, ``allow`` DocType, value, for one DocType or all)
narrowed every role of the user; a scoped role assignment (a ``UserRole`` row
with ``scope_doctype`` / ``scope_value``) narrows only its own role. For each
user with User Permissions:

* a role of the user is *touched* by a User Permission when the role has a rule
  on a DocType it restricted - ``applicable_for``, or (for "all DocTypes") any
  DocType that is, or links to, ``allow``;
* the user's assignment of a touched role (one without a scope) is replaced by
  scoped ones - one per restricted value (rows of one ``allow`` widen each
  other, of different ones narrow: the same as before for that role);
* the User Permissions that touched a role are deleted; one that touched none
  (it narrowed only rules for ``All``, say) stays and is logged - removing
  ``UserPermission`` (step 4c) would drop it.

A role holding every permission (``*``) is never scoped: User Permissions
didn't bind it either. The scope columns are added when the DocType sync
hasn't run yet.

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
_SCOPE_COLUMNS = {
    "scope_doctype": sa.Text(),
    "scope_value": sa.Text(),
    "valid_from": sa.Date(),
    "valid_to": sa.Date(),
}
_LINKS = ("Link", "MultiLink")


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _definitions(conn: sa.Connection) -> dict[str, dict]:
    meta = sa.table(_META, sa.column("name"), sa.column("definition"))
    return {
        name: _json(d) or {} for name, d in conn.execute(sa.select(meta.c.name, meta.c.definition))
    }


def _links_to(definition: dict, name: str, allow: str) -> bool:
    """Whether DocType *name* is, or links to, *allow* (not through a field
    that ignores User Permissions)."""
    if name == allow:
        return True
    return any(
        f.get("fieldtype") in _LINKS
        and f.get("options") == allow
        and not f.get("ignore_user_permissions")
        for f in definition.get("fields") or []
    )


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
        used: set[str] = set()  # UserPermission names that touched a role
        next_idx = max((r["idx"] or 0 for r in assigned), default=0)
        for assignment in assigned:
            role = assignment["role_name"]
            if assignment["scope_doctype"] or role in everything:
                continue
            scopes: dict[str, set[str]] = defaultdict(set)
            for up in user_ups:
                if up["apply_to_all_doctypes"]:
                    touched = any(
                        _links_to(definitions.get(dt) or {}, dt, up["allow"]) for dt in ruled[role]
                    )
                else:
                    touched = up["applicable_for"] in ruled[role]
                if touched:
                    scopes[up["allow"]].add(up["for_value"])
                    used.add(up["name"])
            if not scopes:
                continue
            conn.execute(roles_t.delete().where(roles_t.c.name == assignment["name"]))
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
            log.info("0026: %s - role %r scoped to %s", user, role, dict(scopes))
        if used:
            conn.execute(ups.delete().where(ups.c.name.in_(sorted(used))))
        for up in user_ups:
            if up["name"] not in used:
                log.warning(
                    "0026: %s - UserPermission %s=%s (%s) narrows no role of the user; kept",
                    user,
                    up["allow"],
                    up["for_value"],
                    up["applicable_for"] or "all DocTypes",
                )


def downgrade() -> None:
    pass
