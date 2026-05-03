"""Tree service — operations for is_tree DocTypes.

Uses an **adjacency-list** model: each document has a nullable self-referential
Link field (``parent_field`` defined in ``DocType.tree_view``).

Recursive queries (subtree, path to root) use SQL ``WITH RECURSIVE`` —
supported by SQLite ≥ 3.8.3 and all PostgreSQL / MySQL 8 versions.

Public API
----------
``tree_service.get_children(session, doctype, parent_id, ...)``
    Direct children of a node (or root nodes when parent_id is None).

``tree_service.get_tree(session, doctype, root_id, ...)``
    Full subtree as nested dicts ``{id, title, children: [...], ...}``.

``tree_service.get_ancestors(session, doctype, node_id, ...)``
    Ordered list from direct parent up to the root.

``tree_service.move_node(session, doctype, node_id, new_parent_id, user)``
    Re-parent a node; prevents cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, text

from grunt.metadata.compiler import compile_doctype_to_table
from grunt.metadata.registry import doctype_registry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grunt.auth.doctypes.User.User import User

logger = structlog.get_logger()


def _require_tree(dt: Any) -> str:
    """Return the parent_field name or raise 400 if not a tree DocType."""
    if not dt.is_tree or not dt.tree_view:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"DocType '{dt.name}' is not a tree (is_tree=false or tree_view not configured)",
        )
    return dt.tree_view.parent_field


def _title_field(dt: Any) -> str:
    return dt.tree_view.title_field if dt.tree_view else (dt.title_field or "name")


class TreeService:
    # ──────────────────────────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────────────────────────

    async def get_children(
        self,
        session: AsyncSession,
        doctype: str,
        parent_id: str | None = None,
        *,
        fields: list[str] | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return direct children of *parent_id* (or root nodes if None)."""
        dt = await doctype_registry.get(doctype)
        parent_field = _require_tree(dt)
        table = compile_doctype_to_table(dt)
        title_col = _title_field(dt)

        select_cols = self._build_select_cols(table, fields, title_col, parent_field)
        stmt = select(*select_cols)

        pf_col = table.c.get(parent_field)
        if pf_col is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Column '{parent_field}' not found in table for '{doctype}'",
            )

        if parent_id is None:
            stmt = stmt.where((pf_col == None) | (pf_col == ""))  # noqa: E711
        else:
            stmt = stmt.where(pf_col == parent_id)

        # Order by title if available
        title_sa = table.c.get(title_col) or table.c.get("name")
        if title_sa is not None:
            stmt = stmt.order_by(title_sa.asc())

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = [dict(r._mapping) for r in result.fetchall()]

        # Annotate each node with has_children flag
        child_parent_ids = set()
        if rows:
            parent_ids = [r["id"] for r in rows]
            check_stmt = select(pf_col).where(pf_col.in_(parent_ids)).distinct()
            cr = await session.execute(check_stmt)
            child_parent_ids = {r[0] for r in cr.fetchall()}

        for row in rows:
            row["has_children"] = row["id"] in child_parent_ids

        return rows

    async def get_tree(
        self,
        session: AsyncSession,
        doctype: str,
        root_id: str | None = None,
        *,
        fields: list[str] | None = None,
        max_depth: int = 10,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the full subtree as nested dicts.

        ``root_id=None`` returns the entire forest (all root nodes + their subtrees).
        """
        dt = await doctype_registry.get(doctype)
        parent_field = _require_tree(dt)
        table = compile_doctype_to_table(dt)
        title_col = _title_field(dt)
        table_name = table.name

        select_cols = self._build_select_cols(table, fields, title_col, parent_field)
        col_names = [c.key for c in select_cols]

        import re
        def _check_id(s: str) -> str:
            if not re.match(r"^[a-zA-Z0-9_]+$", s):
                raise ValueError(f"Invalid identifier: {s}")
            return s
            
        table_name = _check_id(table.name)
        pf = _check_id(parent_field)
        
        if root_id is None:
            # Start from root nodes
            anchor_where = f'("{pf}" IS NULL OR "{pf}" = \'\')'
            anchor_param: dict[str, Any] = {}
        else:
            anchor_where = f'"{pf}" = :root_id'
            anchor_param = {"root_id": root_id}

        col_list = ", ".join(f't."{_check_id(c)}"' for c in col_names)
        cte_cols = ", ".join(f'"{_check_id(c)}"' for c in col_names)

        sql = text(f"""
            WITH RECURSIVE tree AS (
                SELECT {col_list}, 0 AS _depth
                FROM "{table_name}" t
                WHERE {anchor_where}
              UNION ALL
                SELECT {col_list}, tree._depth + 1
                FROM "{table_name}" t
                JOIN tree ON t."{pf}" = tree.id
                WHERE tree._depth < :max_depth
            )
            SELECT {cte_cols}, _depth FROM tree
        """)

        result = await session.execute(sql, {**anchor_param, "max_depth": max_depth})
        all_rows = [dict(zip([*col_names, "_depth"], r, strict=False)) for r in result.fetchall()]

        # ── Fast-filter: keep matched nodes + all their ancestors ──────────
        if filters:
            from grunt.document.query import _apply_filters  # noqa: PLC0415

            # Build parent lookup from the flat result set (avoids extra DB round-trip)
            parent_lookup: dict[str, str | None] = {
                r["id"]: r.get(parent_field) or None for r in all_rows
            }

            # Resolve matching IDs by running the filters against the DB table,
            # scoped only to the nodes already present in this subtree.
            tree_ids = [r["id"] for r in all_rows]
            filtered_q = select(table.c.id)
            filtered_q = _apply_filters(filtered_q, table, filters)

            # Controller hook: list_filter_extra — allows DocType controllers
            # (e.g. in app code) to inject extra WHERE clauses without touching
            # the framework core.
            from grunt.document.base import Document  # noqa: PLC0415
            from grunt.document.registry import document_registry  # noqa: PLC0415

            ctrl_cls = document_registry.get(doctype)
            if ctrl_cls.list_filter_extra is not Document.list_filter_extra:
                extra_clause = await ctrl_cls.list_filter_extra(session, filters, table)
                if extra_clause is not None:
                    filtered_q = filtered_q.where(extra_clause)

            preserve_ancestors = True
            if ctrl_cls.tree_preserve_ancestors is not Document.tree_preserve_ancestors:
                preserve_ancestors = await ctrl_cls.tree_preserve_ancestors(
                    session, filters, table
                )

            filtered_q = filtered_q.where(table.c.id.in_(tree_ids))
            filtered_result = await session.execute(filtered_q)
            matched_ids: set[str] = {str(r[0]) for r in filtered_result.fetchall()}

            # Collect ancestor IDs for each matched node so the tree stays readable
            keep_ids: set[str] = set(matched_ids)
            if preserve_ancestors:
                for mid in matched_ids:
                    current = parent_lookup.get(mid)
                    while current:
                        keep_ids.add(current)
                        current = parent_lookup.get(current)

            all_rows = [r for r in all_rows if r["id"] in keep_ids]
        # ──────────────────────────────────────────────────────────────────

        # Build nested structure
        return self._nest(all_rows, parent_field, root_id)

    async def get_ancestors(
        self,
        session: AsyncSession,
        doctype: str,
        node_id: str,
        *,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return ordered path from the direct parent up to the root."""
        dt = await doctype_registry.get(doctype)
        parent_field = _require_tree(dt)
        table = compile_doctype_to_table(dt)
        title_col = _title_field(dt)
        table_name = table.name

        select_cols = self._build_select_cols(table, fields, title_col, parent_field)
        col_names = [c.key for c in select_cols]
        import re
        def _check_id(s: str) -> str:
            if not re.match(r"^[a-zA-Z0-9_]+$", s):
                raise ValueError(f"Invalid identifier: {s}")
            return s

        table_name = _check_id(table.name)
        col_list = ", ".join(f't."{_check_id(c)}"' for c in col_names)
        cte_cols = ", ".join(f'"{_check_id(c)}"' for c in col_names)
        pf = _check_id(parent_field)

        sql = text(f"""
            WITH RECURSIVE ancestors AS (
                SELECT {col_list}, 0 AS _depth
                FROM "{table_name}" t
                WHERE t.id = :node_id
              UNION ALL
                SELECT {col_list}, ancestors._depth + 1
                FROM "{table_name}" t
                JOIN ancestors ON t.id = ancestors."{pf}"
                WHERE ancestors."{pf}" IS NOT NULL
                  AND ancestors."{pf}" != ''
            )
            SELECT {cte_cols} FROM ancestors WHERE id != :node_id ORDER BY _depth DESC
        """)

        result = await session.execute(sql, {"node_id": node_id})
        return [dict(zip(col_names, r, strict=False)) for r in result.fetchall()]

    # ──────────────────────────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────────────────────────

    async def move_node(
        self,
        session: AsyncSession,
        doctype: str,
        node_id: str,
        new_parent_id: str | None,
        user: User,
    ) -> dict[str, Any]:
        """Re-parent *node_id* to *new_parent_id* (or make it a root node).

        Prevents cycles: new_parent must not be in the node's own subtree.
        """
        from datetime import UTC, datetime  # noqa: PLC0415

        from sqlalchemy import update as sa_update  # noqa: PLC0415

        dt = await doctype_registry.get(doctype)
        parent_field = _require_tree(dt)
        table = compile_doctype_to_table(dt)

        # Cycle guard: get subtree ids of the node being moved
        if new_parent_id:
            subtree = await self.get_tree(session, doctype, root_id=node_id)
            subtree_ids = self._collect_ids(subtree)
            if new_parent_id in subtree_ids:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail="Cannot move a node into its own subtree (cycle detected)",
                )

        stmt = (
            sa_update(table)
            .where(table.c.id == node_id)
            .values(
                **{parent_field: new_parent_id or None},
                modified_at=datetime.now(UTC),
                modified_by=user.email,
            )
            .returning(*table.c)
        )
        result = await session.execute(stmt)
        await session.commit()
        row = result.fetchone()
        if not row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Node not found")

        logger.info("tree.node_moved", doctype=doctype, node=node_id, new_parent=new_parent_id)
        return dict(row._mapping)

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_select_cols(
        table: Any, fields: list[str] | None, title_col: str, parent_field: str
    ) -> list:
        """Build SA column list: always include id + parent_field + title, then requested extras."""
        always = {"id", parent_field, title_col}
        wanted = set(fields) if fields else {c.key for c in table.c}
        final = always | wanted
        return [table.c[c] for c in final if c in table.c]

    @staticmethod
    def _nest(
        flat: list[dict[str, Any]],
        parent_field: str,
        root_parent_id: str | None,
    ) -> list[dict[str, Any]]:
        """Convert a flat list into nested dicts via ``children`` key.

        Supports both UUID-based and name-based parent_field values, since
        Link fields may store either the document's id or its name field.
        """
        by_id: dict[str, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for row in flat:
            row["children"] = []
            by_id[row["id"]] = row
            name_val = row.get("name")
            if name_val and name_val != row["id"]:
                by_name[name_val] = row

        roots: list[dict[str, Any]] = []
        for row in flat:
            pid = row.get(parent_field)
            if pid:
                parent = by_id.get(pid) or by_name.get(pid)
                if parent and parent["id"] != row["id"]:
                    parent["children"].append(row)
                    continue
            roots.append(row)
        return roots

    @staticmethod
    def _collect_ids(nodes: list[dict[str, Any]]) -> set[str]:
        """Recursively collect all ``id`` values from a nested tree."""
        ids: set[str] = set()
        stack = list(nodes)
        while stack:
            n = stack.pop()
            ids.add(n["id"])
            stack.extend(n.get("children") or [])
        return ids


tree_service = TreeService()
