"""Permission Log - who changed access and when (PERMISSIONS_PLAN step 6b).

The document pipeline calls :func:`record` after a document is stored,
changed or deleted; for the audited DocTypes it writes a ``PermissionLog`` row
with what changed in the fields that decide access:

* ``User`` - its role assignments (role, scope, period) and ``is_active``;
* ``Role`` - its permissions;
* ``DocType`` - its rules (``permissions``);
* ``SharedWith`` / ``DocumentShare`` - every field (a share, a public link).

A value field logs ``{field, old, new}``; a table (roles, rules) logs the
rows ``added`` and ``removed`` - a changed row is one removed and one added.
The row is written in the same transaction as the change, as the system: it
neither depends on the actor's rights nor is skipped by them.
"""

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from grunt.log import log
from grunt.metadata.registry import doctype_registry

LOG_DOCTYPE = "PermissionLog"

#: DocType -> the fields whose changes are logged (``None`` - every field).
AUDITED: dict[str, frozenset[str] | None] = {
    "User": frozenset({"roles", "is_active"}),
    "Role": frozenset({"permissions"}),
    "DocType": frozenset({"permissions"}),
    "SharedWith": None,
    "DocumentShare": None,
}

# Never compared: bookkeeping every save touches.
_SKIP = frozenset(
    {
        "name",
        "owner",
        "created_at",
        "modified_at",
        "modified_by",
        "idx",
        "parent_doctype",
        "parent_name",
        "parent_field",
        "doctype",
        "view_count",
    }
)

# What identifies a table row - everything that decides access, nothing else.
_ROW_KEYS: dict[tuple[str, str], tuple[str, ...]] = {
    ("User", "roles"): ("role_name", "scope_doctype", "scope_value", "valid_from", "valid_to"),
    ("DocType", "permissions"): (
        "role",
        "actions",
        "match",
        "hidden_fields",
        "readonly_fields",
    ),
}


def is_audited(doctype: str) -> bool:
    return doctype in AUDITED


async def record(
    session: AsyncSession,
    doctype: str,
    doc_id: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    user: str,
) -> None:
    """Write a ``PermissionLog`` row for the change of *doctype* *doc_id* from
    *before* to *after* (``None`` - didn't exist / no longer does). Nothing
    when *doctype* isn't audited or nothing that decides access changed.
    Never raises: a failing log must not undo the change it describes - it is
    logged as an error instead."""
    if doctype not in AUDITED:
        return
    try:
        changes = diff(doctype, before or {}, after or {})
        if not changes:
            return
        meta = await doctype_registry.get_meta(LOG_DOCTYPE)
        if meta is None:
            return
        action = "Created" if before is None else "Deleted" if after is None else "Changed"
        now = datetime.now(UTC)
        async with session.begin_nested():
            await session.execute(
                meta.table.insert().values(
                    name=uuid4().hex[:10],
                    owner=user,
                    created_at=now,
                    modified_at=now,
                    modified_by=user,
                    ref_doctype=doctype,
                    doc_id=str(doc_id),
                    action=action,
                    summary=summary(changes),
                    changes=_jsonable(changes),
                )
            )
    except Exception:
        log.exception("permission_log.write_failed", doctype=doctype, doc_id=doc_id)


def diff(doctype: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    """What changed in *doctype*'s audited fields between *before* and *after*."""
    watched = AUDITED.get(doctype)
    fields = sorted(watched if watched is not None else (set(before) | set(after)) - _SKIP)
    changes: list[dict[str, Any]] = []
    for field in fields:
        old, new = before.get(field), after.get(field)
        if isinstance(old, list) or isinstance(new, list):
            keys = _ROW_KEYS.get((doctype, field))
            old_rows = {_row_key(r, keys) for r in old or []}
            new_rows = {_row_key(r, keys) for r in new or []}
            added = sorted(new_rows - old_rows)
            removed = sorted(old_rows - new_rows)
            if added or removed:
                changes.append(
                    {
                        "field": field,
                        "added": [_row_dict(r) for r in added],
                        "removed": [_row_dict(r) for r in removed],
                    }
                )
        elif _norm(old) != _norm(new):
            changes.append({"field": field, "old": _norm(old), "new": _norm(new)})
    return changes


def summary(changes: Iterable[Mapping[str, Any]]) -> str:
    """One line per change - ``+ row`` / ``- row`` for tables, ``old → new``
    for values (language-neutral: values, not prose)."""
    lines: list[str] = []
    for change in changes:
        field = change["field"]
        if "added" in change:
            lines += [f"{field}: + {_row_text(r)}" for r in change["added"]]
            lines += [f"{field}: − {_row_text(r)}" for r in change["removed"]]
        else:
            lines.append(f"{field}: {_text(change['old'])} → {_text(change['new'])}")
    return "\n".join(lines)


def _row_key(row: Any, keys: tuple[str, ...] | None) -> tuple[tuple[str, Any], ...]:
    """A table row (or a list item) as a hashable, comparable value."""
    if not isinstance(row, Mapping):
        return (("value", _norm(row)),)
    names = keys if keys is not None else sorted(set(row) - _SKIP)
    return tuple((k, _norm(row.get(k))) for k in names if _norm(row.get(k)) is not None)


def _row_dict(key: tuple[tuple[str, Any], ...]) -> Any:
    if len(key) == 1 and key[0][0] == "value":
        return key[0][1]
    return {k: _thaw(v) for k, v in key}


def _row_text(row: Any) -> str:
    if not isinstance(row, Mapping):
        return _text(row)
    first, *rest = list(row.items()) or [("", "")]
    head = _text(first[1])
    tail = ", ".join(f"{k}={_text(v)}" for k, v in rest)
    return f"{head} ({tail})" if tail else head


def _norm(value: Any) -> Any:
    """Comparable and hashable: lists -> sorted tuples, empty -> ``None``,
    dates -> ISO text."""
    if value in (None, "", [], {}):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()[: 10 if not isinstance(value, datetime) else 19]
    if isinstance(value, (list, tuple, set)):
        items = [_norm(v) for v in value]
        return tuple(sorted((i for i in items if i is not None), key=str))
    if isinstance(value, Mapping):
        return tuple(sorted((k, _norm(v)) for k, v in value.items() if k not in _SKIP))
    return value


def _thaw(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _text(value: Any) -> str:
    if value is None:
        return "∅"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_text(v) for v in value) + "]"
    return str(value)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
