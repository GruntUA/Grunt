"""Child table and MultiLink relationship management for Documents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from grunt.document.serde import audit_fields, serialize_datetimes
from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType

logger = structlog.get_logger()

_EXTRA_INJECT = ("color", "icon")

# Columns present in every child table row that carry no value for callers:
# parent linkage is implicit, audit fields are not rendered in child rows.
_CHILD_SKIP_COLS: frozenset[str] = frozenset(
    {
        "parent_name",
        "parent_doctype",
        "parent_field",
        "owner",
        "created_at",
        "modified_at",
        "modified_by",
        "docstatus",
    }
)


async def _resolve_link_labels(
    session: AsyncSession,
    dt: Any,
    rows: list[dict[str, Any]],
) -> None:
    """Inject ``fieldname__label`` (and extra display fields) for Link fields."""
    if not rows:
        return

    link_fields = [f for f in dt.fields if f.fieldtype == "Link" and f.options]
    present_keys = set(rows[0].keys())
    link_fields = [f for f in link_fields if f.fieldname in present_keys]

    if not link_fields:
        return

    for lf in link_fields:
        try:
            target_dt = await doctype_registry.get(lf.options)
        except Exception as exc:
            logger.warning(
                "link_labels.target_doctype_error", doctype=lf.options, error=str(exc)
            )
            continue

        title_field = getattr(target_dt, "title_field", "name") or "name"
        target_table = compile_doctype_to_table(target_dt)

        raw_ids: set[str] = {
            str(row[lf.fieldname]) for row in rows if row.get(lf.fieldname) not in (None, "")
        }
        if not raw_ids:
            continue

        cols_to_fetch = [target_table.c.name]
        if title_field != "name" and title_field in target_table.c:
            cols_to_fetch.append(target_table.c[title_field])

        linked_field_names = {f.fieldname for f in target_dt.fields}
        extra_to_fetch = [
            fname
            for fname in _EXTRA_INJECT
            if fname in linked_field_names and fname in target_table.c
        ]
        for fname in extra_to_fetch:
            cols_to_fetch.append(target_table.c[fname])

        # image_field is doctype-specific (e.g. "photo" on Employee) — always
        # surfaced to the caller as a fixed "image" key regardless of the
        # target's own field name, so list-cell renderers have one contract.
        image_field = getattr(target_dt, "image_field", None)
        has_image = bool(
            image_field and image_field in linked_field_names and image_field in target_table.c
        )
        if has_image and image_field not in {c.key for c in cols_to_fetch}:
            cols_to_fetch.append(target_table.c[image_field])

        q = select(*cols_to_fetch).where(target_table.c.name.in_(raw_ids))

        try:
            async with session.begin_nested():
                result = await session.execute(q)
                linked_rows = result.mappings().all()
        except Exception as exc:
            logger.warning(
                "link_labels.fetch_error", doctype=lf.options, field=lf.fieldname, error=str(exc)
            )
            continue

        label_map: dict[str, str] = {}
        image_map: dict[str, Any] = {}
        extra_maps: dict[str, dict[str, Any]] = {fname: {} for fname in extra_to_fetch}
        for lr in linked_rows:
            label = str(lr.get(title_field) or lr.get("name") or "")
            for key in (str(lr["name"]),):
                label_map[key] = label
                for fname in extra_to_fetch:
                    val = lr.get(fname)
                    if val is not None:
                        extra_maps[fname][key] = val
                if has_image:
                    img_val = lr.get(image_field)
                    if img_val:
                        image_map[key] = img_val

        label_key = f"{lf.fieldname}__label"
        image_key = f"{lf.fieldname}__image"
        for row in rows:
            raw = row.get(lf.fieldname)
            if raw not in (None, ""):
                raw_str = str(raw)
                row[label_key] = label_map.get(raw_str, raw_str)
                for fname in extra_to_fetch:
                    val = extra_maps[fname].get(raw_str)
                    if val is not None:
                        row[f"{lf.fieldname}__{fname}"] = val
                if has_image:
                    # Always set the key (even "") when the target doctype
                    # supports avatars, so the frontend can render an
                    # initials-fallback circle for records with no image yet
                    # — distinct from Link fields with no avatar concept at all.
                    row[image_key] = image_map.get(raw_str, "")


def _get_multi_link_fields(dt: DocType) -> list:
    """Return MultiLink fields from a DocType."""
    return [f for f in dt.fields if f.fieldtype == "MultiLink"]


async def attach_multi_link_values(
    ml: Any,
    doctype_name: str,
    doc_id: str,
    dt: DocType,
    doc: dict[str, Any],
    *,
    fields: set[str] | None = None,
) -> None:
    """Attach MultiLink list values to *doc* in-place.

    ``fields=None`` attaches every MultiLink field; otherwise only the named
    subset is attached. All values are fetched in a single query.
    """
    ml_fields = _get_multi_link_fields(dt)
    if fields is not None:
        ml_fields = [f for f in ml_fields if f.fieldname in fields]
    if not ml_fields:
        return
    ml_data = await ml.get_all_for_doc(doctype_name, doc_id)
    for f in ml_fields:
        doc[f.fieldname] = ml_data.get(f.fieldname, [])


def apply_field_values(
    fields: Any,
    data: dict[str, Any],
    row: dict[str, Any],
    *,
    fill_empty: bool = False,
) -> None:
    """Copy coerced physical-field values from *data* into *row* in-place.

    For each physical field, the value is taken from *data* (coerced), falling
    back to the field default. With ``fill_empty=True`` every physical column is
    written with a type-appropriate empty value when absent from *data* (used for
    child rows to avoid NOT NULL violations); otherwise only Check fields get a
    default ``False``.
    """
    for field in fields:
        if not field.is_physical:
            continue
        if field.fieldname in data:
            row[field.fieldname] = field.coerce(data[field.fieldname])
        elif field.default is not None:
            row[field.fieldname] = field.coerce(field.default)
        elif field.fieldtype == "Check":
            row[field.fieldname] = False
        elif fill_empty:
            if field.fieldtype in ("Int", "Float"):
                row[field.fieldname] = 0
            elif field.fieldtype in ("Date", "Datetime", "Time"):
                row[field.fieldname] = None
            else:
                row[field.fieldname] = ""


async def _load_child_tables(
    session: AsyncSession,
    dt: DocType,
    doc: dict[str, Any],
    include_fields: set[str] | None = None,
) -> None:
    """Attach child table rows to *doc* in-place for all TABLE fields."""
    for field in dt.fields:
        if field.fieldtype != "Table" or not field.options:
            continue
        if include_fields is not None and field.fieldname not in include_fields:
            continue
        try:
            child_dt = await doctype_registry.get(field.options)
            child_table = compile_doctype_to_table(child_dt)
            data_fields = {f.fieldname for f in child_dt.fields if f.is_physical}
            keep = {"name", "idx"} | data_fields
            cols = [c for c in child_table.c if c.key not in _CHILD_SKIP_COLS and c.key in keep]
            result = await session.execute(
                select(*cols)
                .where(child_table.c.parent_name == doc["name"])
                .order_by(child_table.c.idx)
            )
            rows = [dict(r._mapping) for r in result.all()]
            for row in rows:
                serialize_datetimes(row)
            await _resolve_link_labels(session, child_dt, rows)
            doc[field.fieldname] = rows
        except Exception:
            logger.exception("child_table.load_error", doctype=dt.name, field=field.fieldname)
            doc[field.fieldname] = []


def _table_fieldnames(dt: DocType) -> set[str]:
    """Return all child-table fieldnames for a DocType."""
    return {f.fieldname for f in dt.fields if f.fieldtype == "Table" and bool(f.options)}


async def _save_child_tables(
    session: AsyncSession,
    dt: DocType,
    parent_id: str,
    data: dict[str, Any],
    user: User,
    now: datetime,
) -> None:
    """Replace child table rows for all TABLE fields present in *data*."""
    for field in dt.fields:
        if field.fieldtype != "Table" or not field.options:
            continue
        if field.fieldname not in data:
            continue
        child_rows = data[field.fieldname]
        if not isinstance(child_rows, list):
            child_rows = []

        # Not best-effort: persisting the document is not actually complete
        # until its child rows are, so a failure here must propagate and roll
        # back the transaction rather than report a false success.
        child_dt = await doctype_registry.get(field.options)
        child_table = compile_doctype_to_table(child_dt)
        # Delete existing rows for this parent
        await session.execute(child_table.delete().where(child_table.c.parent_name == parent_id))
        # Build all rows then insert in one batch
        rows_to_insert: list[dict[str, Any]] = []
        for idx, child_data in enumerate(child_rows):
            if not isinstance(child_data, dict):
                continue
            # Always use the array position as the canonical idx so that
            # drag-and-drop reordering on the client is faithfully persisted.
            # The client-side `idx` field is intentionally ignored here because
            # it may carry stale values from a previous save.
            child_idx = idx
            row: dict[str, Any] = {
                "name": f"{parent_id}-{field.fieldname}-{child_idx}",
                "parent_name": parent_id,
                "parent_doctype": dt.name,
                "parent_field": field.fieldname,
                "idx": child_idx,
                **audit_fields(user.email, now),
            }
            # Always include every column to avoid NOT NULL constraint errors.
            apply_field_values(child_dt.fields, child_data, row, fill_empty=True)
            rows_to_insert.append(row)
        if rows_to_insert:
            await session.execute(child_table.insert(), rows_to_insert)
