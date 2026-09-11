"""Child table and MultiLink relationship management for Documents."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from grunt.document.meta import Meta
from grunt.document.serde import audit_fields, serialize_datetimes
from grunt.log import log
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.user import User
    from grunt.metadata.doctype import DocType


# Target-doctype fields auto-injected alongside a Link field's __label (as
# __color/__icon) when the target defines them — list-cell badges and map
# markers render a linked record's color/icon without a separate fetch.
# See frontend/src/components/fields/Link/ListCell.vue and useMapMarkers.ts.
_EXTRA_INJECT = ("color", "icon")

# Extracts the ?file_id=... query param from an Attach field's stored URL
# (grunt.storage.doctypes.File.file.get_content?file_id=...). Mirrors
# frontend/src/components/fields/Attach/Attach.vue's extractFileId().
_ATTACH_FILE_ID_RE = re.compile(r"[?&]file_id=([^&]+)")

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

    for lf in link_fields:
        await _inject_link_field_labels(session, lf, rows)


async def _inject_link_field_labels(
    session: AsyncSession, lf: Any, rows: list[dict[str, Any]]
) -> None:
    """Load display label (+ extras/image) for one Link field and write it onto *rows*."""
    try:
        target_dt = await doctype_registry.get(lf.options)
    except Exception as exc:
        log.warning("link_labels.target_doctype_error", doctype=lf.options, error=str(exc))
        return

    target_meta = Meta(target_dt)
    title_field = target_meta.get_title_field()
    target_table = target_meta.table

    raw_ids: set[str] = {
        str(row[lf.fieldname]) for row in rows if row.get(lf.fieldname) not in (None, "")
    }
    if not raw_ids:
        return

    cols_to_fetch, extra_to_fetch, image_field, has_image = _link_display_columns(
        target_meta, target_table, title_field
    )
    q = select(*cols_to_fetch).where(target_table.c.name.in_(raw_ids))

    try:
        async with session.begin_nested():
            result = await session.execute(q)
            linked_rows = result.mappings().all()
    except Exception as exc:
        log.warning(
            "link_labels.fetch_error", doctype=lf.options, field=lf.fieldname, error=str(exc)
        )
        return

    label_map, extra_maps, image_map = _build_link_lookup_maps(
        linked_rows, title_field, extra_to_fetch, image_field, has_image
    )
    _apply_link_labels(rows, lf.fieldname, label_map, extra_maps, image_map, has_image)


def _link_display_columns(
    target_meta: Meta, target_table: Any, title_field: str
) -> tuple[list[Any], list[str], str | None, bool]:
    """Return (columns to SELECT, extra field names, image field name, has_image)."""
    cols_to_fetch = [target_table.c.name]
    if title_field != "name" and title_field in target_table.c:
        cols_to_fetch.append(target_table.c[title_field])

    extra_to_fetch = [
        fname for fname in _EXTRA_INJECT if target_meta.has_field(fname) and fname in target_table.c
    ]
    for fname in extra_to_fetch:
        cols_to_fetch.append(target_table.c[fname])

    # image_field is doctype-specific (e.g. "photo" on Employee) — always
    # surfaced to the caller as a fixed "image" key regardless of the
    # target's own field name, so list-cell renderers have one contract.
    image_field = target_meta.get_image_field()
    has_image = bool(image_field and image_field in target_table.c)
    if has_image and image_field not in {c.key for c in cols_to_fetch}:
        cols_to_fetch.append(target_table.c[image_field])

    return cols_to_fetch, extra_to_fetch, image_field, has_image


def _build_link_lookup_maps(
    linked_rows: Any,
    title_field: str,
    extra_to_fetch: list[str],
    image_field: str | None,
    has_image: bool,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, Any]]:
    """Build name -> (label, extra field value, image value) lookup maps from fetched rows."""
    label_map: dict[str, str] = {}
    image_map: dict[str, Any] = {}
    extra_maps: dict[str, dict[str, Any]] = {fname: {} for fname in extra_to_fetch}
    for lr in linked_rows:
        key = str(lr["name"])
        label_map[key] = str(lr.get(title_field) or lr.get("name") or "")
        for fname in extra_to_fetch:
            val = lr.get(fname)
            if val is not None:
                extra_maps[fname][key] = val
        if has_image:
            img_val = lr.get(image_field)
            if img_val:
                image_map[key] = img_val
    return label_map, extra_maps, image_map


def _apply_link_labels(
    rows: list[dict[str, Any]],
    fieldname: str,
    label_map: dict[str, str],
    extra_maps: dict[str, dict[str, Any]],
    image_map: dict[str, Any],
    has_image: bool,
) -> None:
    """Write ``fieldname__label``/``__<extra>``/``__image`` onto each row, from the lookup maps."""
    label_key = f"{fieldname}__label"
    image_key = f"{fieldname}__image"
    for row in rows:
        raw = row.get(fieldname)
        if raw in (None, ""):
            continue
        raw_str = str(raw)
        row[label_key] = label_map.get(raw_str, raw_str)
        for fname, values in extra_maps.items():
            val = values.get(raw_str)
            if val is not None:
                row[f"{fieldname}__{fname}"] = val
        if has_image:
            # Always set the key (even "") when the target doctype supports
            # avatars, so the frontend can render an initials-fallback circle
            # for records with no image yet — distinct from Link fields with
            # no avatar concept at all.
            row[image_key] = image_map.get(raw_str, "")


async def _resolve_attach_labels(
    session: AsyncSession,
    dt: Any,
    rows: list[dict[str, Any]],
) -> None:
    """Inject ``fieldname__label`` (the real filename) for Attach fields.

    An Attach value is a download URL keyed by ``file_id``, not a filename —
    list/grid cells that show it raw are useless to the user (see
    frontend/src/components/fields/Table/Table.vue's ``cellDisplay``, which
    reads this the same way it reads a Link field's ``__label``).
    """
    if not rows:
        return

    attach_fields = [f for f in dt.fields if f.fieldtype == "Attach"]
    present_keys = set(rows[0].keys())
    attach_fields = [f for f in attach_fields if f.fieldname in present_keys]

    for af in attach_fields:
        await _inject_attach_field_labels(session, af, rows)


async def _inject_attach_field_labels(
    session: AsyncSession, af: Any, rows: list[dict[str, Any]]
) -> None:
    """Resolve each row's stored ``file_id`` to its real filename via ``File``."""
    file_id_by_row_idx: dict[int, str] = {}
    for i, row in enumerate(rows):
        raw = row.get(af.fieldname)
        if not raw:
            continue
        match = _ATTACH_FILE_ID_RE.search(str(raw))
        if match:
            file_id_by_row_idx[i] = match.group(1)

    if not file_id_by_row_idx:
        return

    try:
        file_dt = await doctype_registry.get("File")
    except Exception as exc:
        log.warning("attach_labels.file_doctype_error", error=str(exc))
        return

    file_table = Meta(file_dt).table
    file_ids = set(file_id_by_row_idx.values())

    try:
        async with session.begin_nested():
            result = await session.execute(
                select(file_table.c.name, file_table.c.file_name).where(
                    file_table.c.name.in_(file_ids)
                )
            )
            name_map = {str(r.name): r.file_name for r in result.all()}
    except Exception as exc:
        log.warning("attach_labels.fetch_error", field=af.fieldname, error=str(exc))
        return

    label_key = f"{af.fieldname}__label"
    for i, file_id in file_id_by_row_idx.items():
        label = name_map.get(file_id)
        if label:
            rows[i][label_key] = label


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
    ml_fields = Meta(dt).get_multilink_fields()
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
    for field in Meta(dt).get_child_table_fields():
        if include_fields is not None and field.fieldname not in include_fields:
            continue
        try:
            child_dt = await doctype_registry.get(field.options)
            child_meta = Meta(child_dt)
            child_table = child_meta.table
            data_fields = {f.fieldname for f in child_meta.get_physical_fields()}
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
            await _resolve_attach_labels(session, child_dt, rows)
            doc[field.fieldname] = rows
        except Exception:
            log.exception("child_table.load_error", doctype=dt.name, field=field.fieldname)
            doc[field.fieldname] = []


async def _save_child_tables(
    session: AsyncSession,
    dt: DocType,
    parent_id: str,
    data: dict[str, Any],
    user: User,
    now: datetime,
) -> None:
    """Replace child table rows for all TABLE fields present in *data*."""
    for field in Meta(dt).get_child_table_fields():
        if field.fieldname not in data:
            continue
        child_rows = data[field.fieldname]
        if not isinstance(child_rows, list):
            child_rows = []

        # Not best-effort: persisting the document is not actually complete
        # until its child rows are, so a failure here must propagate and roll
        # back the transaction rather than report a false success.
        child_dt = await doctype_registry.get(field.options)
        child_table = Meta(child_dt).table
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
