"""``__child_of`` filters - expanded to ``__in`` over a tree before parsing.

The list search box is :func:`grunt.store.sql.search_condition`."""

from typing import Any

from sqlalchemy import select

import grunt
from grunt.document.meta import Meta
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
