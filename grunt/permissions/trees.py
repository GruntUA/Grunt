"""Subtrees of tree DocTypes - a scope (or a shared node) on a parent covers
every node beneath it (an institution -> all its sub-departments)."""

from grunt.db.api import GruntDB
from grunt.metadata.registry import doctype_registry

_db = GruntDB()  # stateless: reads through the context's session


async def expand_tree_values(doctype: str, values: set[str]) -> set[str]:
    """When *doctype* is a tree DocType, widen *values* to every descendant.

    A non-tree DocType - the common case - returns *values* unchanged after a
    single in-memory registry hit. A tree costs a couple of small indexed
    queries per call; departments / units / folders are few enough that
    caching isn't worth the staleness risk.
    """
    dt = await doctype_registry.get_meta(doctype)
    if dt is None:
        return values
    parent_field = getattr(dt, "tree_parent_field", None)
    if not getattr(dt, "is_tree", False) or not parent_field:
        return values

    out = set(values)
    frontier = list(values)
    while frontier:
        rows = await _db.get_all(
            doctype,
            filters={f"{parent_field}__in": frontier},
            fields=["name"],
            limit=None,
        )
        children = [r["name"] for r in rows if r["name"] not in out]
        out.update(children)
        frontier = children
    return out
