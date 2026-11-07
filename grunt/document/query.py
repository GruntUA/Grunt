"""Query and filter building for document list queries."""

from typing import Any

from sqlalchemy import or_, select

import grunt
from grunt.db.dialects import current_dialect
from grunt.document.meta import Meta
from grunt.search.terms import like_term, match_terms
lazy from grunt.metadata.doctype import DocType

# Filters become a query predicate in grunt.query.sql.filter_expr (parsed by
# grunt.query.parse) - no filter building lives here.


async def expand_child_of_filters(
    session: Any,
    dt: DocType,
    filters: dict[str, str],
) -> dict[str, str]:
    """Expand ``field__child_of=X`` into ``field__in=X,child1,...`` via BFS.

    Unknown fields or non-tree linked doctypes fall back to ``field__eq``.
    """
    result: dict[str, str] = {}
    for key, value in filters.items():
        if not key.endswith("__child_of"):
            result[key] = value
            continue

        fieldname = key[: -len("__child_of")]

        field = Meta(dt).get_field(fieldname)
        if not field or not getattr(field, "options", None):
            result[f"{fieldname}__eq"] = value
            continue

        linked_doctype: str = field.options  # type: ignore[assignment]

        linked_dt = await grunt.get_meta(linked_doctype)
        if linked_dt is None:
            result[f"{fieldname}__eq"] = value
            continue

        if not linked_dt.is_tree:
            result[f"{fieldname}__eq"] = value
            continue

        tree_view = linked_dt.get_tree_view()
        parent_field: str = (
            tree_view.parent_field if tree_view and tree_view.parent_field else "parent"
        )

        linked_table = linked_dt.table
        parent_col = linked_table.c.get(parent_field)
        if parent_col is None:
            result[f"{fieldname}__eq"] = value
            continue

        # BFS: collect root + all descendants
        all_ids: list[str] = [value]
        to_expand: list[str] = [value]
        while to_expand:
            q = select(linked_table.c.name).where(parent_col.in_(to_expand))
            rows = await session.execute(q)
            children = [str(r[0]) for r in rows if str(r[0]) not in all_ids]
            all_ids.extend(children)
            to_expand = children

        result[f"{fieldname}__in"] = ",".join(all_ids)

    return result


async def _linked_search_columns(field: Any) -> tuple[Any, list[Any]] | None:
    """Resolve the *linked* table and its identifier columns (name, title,
    search fields) for a Link field, so a search matches what the user sees
    rather than the raw id stored in the column.

    Returns ``None`` if the linked DocType can't be resolved (e.g. options
    missing) - the caller then falls back to matching the raw column.
    """
    linked_doctype = getattr(field, "options", None)
    if not linked_doctype:
        return None

    linked_dt = await grunt.get_meta(linked_doctype)
    if linked_dt is None:
        return None

    linked_table = linked_dt.table
    linked_cols = [linked_table.c.name]
    seen = {"name"}
    for fname in [linked_dt.title_field, *(linked_dt.search_fields or [])]:
        if not fname or fname in seen:
            continue
        col = linked_table.c.get(fname)
        if col is not None:
            linked_cols.append(col)
            seen.add(fname)
    return linked_table, linked_cols


async def _apply_search(query: Any, table: Any, dt: DocType, search: str) -> Any:
    """Apply the list-view search box to a statement.

    Searched columns: ``name``, the ``title_field`` and every declared
    ``search_fields`` entry. The query is split into terms; a row matches
    when every term is found in some searched column (see
    :mod:`grunt.search.terms`), so «Іван Петренко» finds a row whose first
    and last name are separate fields.

    Link fields in ``search_fields`` are matched against the *linked*
    document's title/search fields rather than the raw id stored in the
    column, since a user searching a list types the person/item's name,
    not its internal id.
    """
    meta = Meta(dt)
    dialect = current_dialect()
    direct_cols: list[Any] = [table.c.name]
    link_targets: list[tuple[Any, Any, list[Any]]] = []
    seen = {"name"}
    for fname in [dt.title_field, *(dt.search_fields or [])]:
        if not fname or fname in seen:
            continue
        seen.add(fname)
        col = table.c.get(fname)
        if col is None:
            continue
        field = meta.get_field(fname)
        if field is not None and field.has_trait("link"):
            resolved = await _linked_search_columns(field)
            if resolved is not None:
                link_targets.append((col, *resolved))
                continue
        direct_cols.append(col)

    def term_condition(term: str) -> Any:
        conditions = [like_term(c, term, dialect) for c in direct_cols]
        for col, linked_table, linked_cols in link_targets:
            linked_match = or_(*(like_term(c, term, dialect) for c in linked_cols))
            conditions.append(col.in_(select(linked_table.c.name).where(linked_match)))
        return or_(*conditions)

    condition = match_terms(search, term_condition)
    return query if condition is None else query.where(condition)
