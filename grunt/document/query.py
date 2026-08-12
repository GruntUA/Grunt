"""Query and filter building for document list queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select

from grunt.db.api import build_clauses

if TYPE_CHECKING:
    from grunt.metadata.doctype import DocType


def _apply_filters(query: Any, table: Any, filters: dict[str, str]) -> Any:
    """Apply operator-aware dictionary filters to a statement.

    Delegates clause building to the single shared parser in ``grunt.db.api``.
    """
    for clause in build_clauses(table, filters):
        query = query.where(clause)
    return query


async def _expand_child_of_filters(
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

        from grunt.document.meta import Meta

        field = Meta(dt).get_field(fieldname)
        if not field or not getattr(field, "options", None):
            result[f"{fieldname}__eq"] = value
            continue

        linked_doctype: str = field.options  # type: ignore[assignment]

        from grunt.metadata.registry import doctype_registry

        try:
            linked_dt = await doctype_registry.get(linked_doctype)
        except Exception:
            result[f"{fieldname}__eq"] = value
            continue

        if not linked_dt.is_tree:
            result[f"{fieldname}__eq"] = value
            continue

        tree_view = getattr(linked_dt, "tree_view", None)
        parent_field: str = (
            tree_view.parent_field if tree_view and tree_view.parent_field else "parent"
        )

        from grunt.metadata.compiler import compile_doctype_to_table

        linked_table = compile_doctype_to_table(linked_dt)
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


def _apply_search(query: Any, table: Any, dt: DocType, search: str) -> Any:
    """Apply full-text search conditions to a statement."""
    search_cols = [table.c.name]
    if dt.search_fields:
        for fname in dt.search_fields:
            col = table.c.get(fname)
            if col is not None and col.name != "name":
                search_cols.append(col)

    conditions = [col.ilike(f"%{search}%") for col in search_cols]
    return query.where(or_(*conditions))
