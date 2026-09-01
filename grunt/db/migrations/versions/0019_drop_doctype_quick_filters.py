"""Drop the ``quick_filters`` child table — quick filters come from field flags.

The list/tree toolbar filter set is no longer configured through a dedicated
``quick_filters`` child table (backed by ``DocTypeQuickFilter``). It is derived
entirely from fields flagged ``in_quick_filter`` in the designer.

For every stored DocType in ``grunt_meta_doctype`` this migration:

* flips ``in_quick_filter = true`` on each field referenced by an existing
  ``data["quick_filters"]`` entry, so shipped filter sets survive the switch;
* removes the ``data["quick_filters"]`` list;
* for the ``DocType`` meta row itself, also strips the now-dead ``quick_filters``
  Table field and its ``sec_list_view`` section from ``data["fields"]``.

Per-filter customisation that had no field-level equivalent (custom operator,
label override, explicit ``options``, ``on_change`` / ``default_value``,
per-filter ``enabled_in``) is dropped. ``DocType.json`` and the ``DocType``
Pydantic model have already been updated; ``_inject_core`` never removes
stored-only keys, so this one-shot surgical cleanup runs on every site.

``grunt_meta_doctype.data`` is a ``JSON`` column: reading yields a ``dict`` and
writing a ``dict`` serialises it once. A row that comes back as a ``str`` was
stored double-encoded (a JSON string wrapping the JSON object) — this migration
also rewrites those as plain objects, so it is safe to re-run.

Revision ID: 0019_drop_doctype_quick_filters
Revises: 0018_drop_doctype_dead_tabs
Create Date: 2026-09-01
"""

from __future__ import annotations

import json
import logging

import sqlalchemy as sa
from alembic import op

revision = "0019_drop_doctype_quick_filters"
down_revision = "0018_drop_doctype_dead_tabs"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

_DROP_META_FIELDS = {"quick_filters", "sec_list_view"}


def _as_dict(raw: object) -> dict | None:
    """Unwrap ``data`` to a dict, tolerating one or more JSON-string layers."""
    value = raw
    for _ in range(4):
        if isinstance(value, dict):
            return value
        if isinstance(value, (str, bytes)):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
        else:
            return None
    return None


def upgrade() -> None:
    conn = op.get_bind()
    meta = sa.MetaData()
    tbl = sa.Table("grunt_meta_doctype", meta, autoload_with=conn)

    converted = 0
    for row in conn.execute(sa.select(tbl.c.name, tbl.c.data)).fetchall():
        data = _as_dict(row.data)
        if data is None:
            continue

        # A JSON column returns a dict for a well-formed row; a str means the
        # value was stored double-encoded. Rewriting `data` below normalises it.
        changed = not isinstance(row.data, dict)

        fields = data.get("fields")
        fields = fields if isinstance(fields, list) else []

        qfs = data.pop("quick_filters", None)
        if qfs is not None:
            changed = True
            if isinstance(qfs, list):
                flagged = {
                    qf["field"]
                    for qf in qfs
                    if isinstance(qf, dict) and qf.get("field")
                }
                for f in fields:
                    if f.get("fieldname") in flagged:
                        f["in_quick_filter"] = True

        if row.name == "DocType" and fields:
            kept = [f for f in fields if f.get("fieldname") not in _DROP_META_FIELDS]
            if len(kept) != len(fields):
                data["fields"] = kept
                changed = True

        if changed:
            conn.execute(
                tbl.update().where(tbl.c.name == row.name).values(data=data)
            )
            converted += 1

    log.info("0019: normalised quick_filters on %d DocType definition(s)", converted)


def downgrade() -> None:
    # The child-table shape is gone for good — irreversible.
    pass
