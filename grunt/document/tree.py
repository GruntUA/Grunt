"""Tree service - operations for is_tree DocTypes.

Uses an **adjacency-list** model: each document has a nullable self-referential
Link field (``parent_field`` defined in ``DocType.tree_view``).

Recursive queries (subtree, path to root) use a SQLAlchemy Core recursive CTE
(``Select.cte(recursive=True)``) - supported by SQLite ≥ 3.8.3 and all
PostgreSQL / MySQL 8 versions.

Public API
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

from fastapi import HTTPException, status
from sqlalchemy import literal, select

from grunt import _, log
from grunt.document.registry import document_registry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

    from grunt.auth.doctypes.User.user import User


# doctype -> async fn(session, nodes, as_of_date) -> {node_id: display_title}
#
# Lets an app attach point-in-time display labels to its own tree DocType
# (e.g. "what was this node called on 2024-01-01") without the framework's
# generic Tree API needing to know that app's DocTypes or business terms -
# apps register via grunt.document.tree.register_tree_title_resolver(...) in
# their own hooks.py, loaded by main.py alongside doc_events/scheduler_events.
TREE_TITLE_RESOLVERS: dict[str, Callable[..., Awaitable[dict[str, str]]]] = {}


def register_tree_title_resolver(
    doctype: str, resolver: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    """Register *resolver* to compute historical display titles for *doctype* trees.

    ``resolver(session, nodes, as_of_date) -> {node_id: display_title}`` is
    called by the ``/{doctype}/tree`` API endpoint whenever the request
    includes ``?as_of=<date>``.
    """
    TREE_TITLE_RESOLVERS[doctype] = resolver


def flatten_tree_node_ids(nodes: list[dict[str, Any]]) -> list[str]:
    """Collect every node ``name`` in a nested ``{children: [...]}`` tree.

    For title resolvers to look up rows for every node in the (sub)tree
    ``get_tree`` returned, regardless of depth.
    """
    ids: list[str] = []
    stack = list(nodes)
    while stack:
        node = stack.pop()
        node_id = node.get("name")
        if isinstance(node_id, str) and node_id:
            ids.append(node_id)
        children = node.get("children") or []
        if isinstance(children, list):
            stack.extend(children)
    return ids


def _require_tree(dt: Any) -> str:
    """Return the parent_field name or raise 400 if not a tree DocType."""
    if not dt.is_tree or not dt.tree_view:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_("DocType '%(name)s' is not a tree (is_tree=false or tree_view not configured)")
            % {"name": dt.name},
        )
    return dt.tree_view.parent_field


def _title_field(dt: Any) -> str:
    return dt.tree_view.title_field if dt.tree_view else (dt.title_field or "name")


class TreeService:
    # Read

    async def get_children(
        self,
        session: AsyncSession,
        doctype: str,
        parent_id: str | None = None,
        *,
        fields: list[str] | None = None,
        limit: int = 500,
        filters: dict[str, str] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        scope: Select | None = None,
    ) -> list[dict[str, Any]]:
        """Return direct children of *parent_id* (or root nodes if None).

        ``scope`` - a ``SELECT name`` of the nodes the caller may see (row-level
        permissions); a visible node whose parent is outside it counts as a root.
        """
        import grunt

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype},
            )
        parent_field = _require_tree(dt)
        table = dt.table
        title_col = _title_field(dt)

        controller_filters = filters or {}
        sort_by, sort_order = await self._resolve_sort_config(
            session,
            dt,
            table,
            controller_filters,
            explicit_sort_by=sort_by,
            explicit_sort_order=sort_order,
            fallback_field=title_col,
            fallback_if_missing=True,
            controller_cls=document_registry.get(doctype),
        )

        select_cols = self._build_select_cols(
            table,
            fields,
            title_col,
            parent_field,
            sort_by=sort_by,
        )
        stmt = select(*select_cols)

        pf_col = table.c.get(parent_field)
        if pf_col is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_("Column '%(parent_field)s' not found in table for '%(doctype)s'")
                % {"parent_field": parent_field, "doctype": doctype},
            )

        if parent_id is None:
            is_root = pf_col.is_(None) | (pf_col == "")
            if scope is not None:
                is_root = is_root | pf_col.not_in(scope)
            stmt = stmt.where(is_root)
        else:
            stmt = stmt.where(pf_col == parent_id)
        if scope is not None:
            stmt = stmt.where(table.c.name.in_(scope))

        sort_col = table.c.get(sort_by) if sort_by else None
        if sort_col is not None:
            stmt = stmt.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
        else:
            # Preserve historic behavior when no valid sort field is resolved.
            title_sa = table.c.get(title_col) or table.c.get("name")
            if title_sa is not None:
                stmt = stmt.order_by(title_sa.asc())

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        rows = [dict(r._mapping) for r in result.fetchall()]

        # Annotate each node with has_children flag
        child_parent_ids = set()
        if rows:
            parent_ids = [r["name"] for r in rows]
            check_stmt = select(pf_col).where(pf_col.in_(parent_ids)).distinct()
            if scope is not None:
                check_stmt = check_stmt.where(table.c.name.in_(scope))
            cr = await session.execute(check_stmt)
            child_parent_ids = {r[0] for r in cr.fetchall()}

        for row in rows:
            row["has_children"] = row["name"] in child_parent_ids

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
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
        scope: Select | None = None,
    ) -> list[dict[str, Any]]:
        """Return the full subtree as nested dicts.

        ``root_id=None`` returns the entire forest (all root nodes + their subtrees).
        ``search`` matches ``name``/title/``search_fields`` (case-insensitive
        substring) and, like ``filters``, keeps the ancestors of every match so
        the returned tree stays connected.
        ``scope`` - a ``SELECT name`` of the nodes the caller may see (row-level
        permissions); the rest are dropped, ancestors included, and a visible
        node whose parent is hidden is returned as a root.
        """
        import grunt
        from grunt.document.base import Document

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype},
            )
        parent_field = _require_tree(dt)
        table = dt.table
        title_col = _title_field(dt)

        ctrl_cls = document_registry.get(doctype)
        controller_filters = filters or {}
        sort_by, sort_order = await self._resolve_sort_config(
            session,
            dt,
            table,
            controller_filters,
            explicit_sort_by=sort_by,
            explicit_sort_order=sort_order,
            fallback_field=title_col,
            fallback_if_missing=False,
            controller_cls=ctrl_cls,
        )

        select_cols = self._build_select_cols(
            table,
            fields,
            title_col,
            parent_field,
            sort_by=sort_by,
        )
        col_names = [c.key for c in select_cols]
        pf_col = table.c[parent_field]

        anchor = select(*select_cols, literal(0).label("_depth"))
        anchor = anchor.where(
            pf_col.is_(None) | (pf_col == "") if root_id is None else pf_col == root_id
        )
        tree_cte = anchor.cte("tree", recursive=True)

        recursive_step = (
            select(*(table.c[c] for c in col_names), (tree_cte.c._depth + 1).label("_depth"))
            .join(tree_cte, table.c[parent_field] == tree_cte.c.name)
            .where(tree_cte.c._depth < max_depth)
        )
        tree_cte = tree_cte.union_all(recursive_step)

        result = await session.execute(select(tree_cte))
        all_rows = [dict(r._mapping) for r in result.fetchall()]

        if scope is not None:
            visible = {str(r[0]) for r in (await session.execute(scope)).fetchall()}
            all_rows = [r for r in all_rows if r["name"] in visible]

        search_term = (search or "").strip()
        if filters or search_term:
            all_rows = await self._apply_quick_filter(
                session,
                table,
                ctrl_cls,
                all_rows,
                parent_field,
                filters or {},
                dt=dt,
                search=search_term or None,
            )

        if sort_by:
            all_rows = self._sort_flat_rows(all_rows, sort_by, sort_order)

        # Build nested structure
        nested = self._nest(all_rows, parent_field, root_id)
        if ctrl_cls.tree_sort_children is not Document.tree_sort_children:
            nested = await self._apply_tree_sort_children_hook(
                ctrl_cls,
                session,
                nested,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        return nested

    async def _apply_quick_filter(
        self,
        session: AsyncSession,
        table: Any,
        ctrl_cls: Any,
        all_rows: list[dict[str, Any]],
        parent_field: str,
        filters: dict[str, str],
        *,
        dt: Any = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Keep only nodes matching *filters*/*search*, plus their ancestors, from *all_rows*.

        Runs the filter against the DB scoped to the ids already fetched into
        this subtree (avoids a second full recursive-CTE round-trip), then
        walks an in-memory parent lookup to keep ancestors so the returned
        tree stays connected/readable instead of showing orphaned matches.
        """
        from grunt.db.filters import apply_filters
        from grunt.document.base import Document

        # Build parent lookup from the flat result set (avoids extra DB round-trip)
        parent_lookup: dict[str, str | None] = {
            r["name"]: r.get(parent_field) or None for r in all_rows
        }

        # Resolve matching IDs by running the filters against the DB table,
        # scoped only to the nodes already present in this subtree.
        tree_ids = [r["name"] for r in all_rows]
        filtered_q = select(table.c.name)
        filtered_q = apply_filters(filtered_q, table, filters)

        if search:
            from sqlalchemy import or_

            candidate_fields: list[str] = []
            if dt is not None:
                title_field = _title_field(dt)
                if title_field:
                    candidate_fields.append(title_field)
                candidate_fields.extend(getattr(dt, "search_fields", None) or [])
            seen = {"name"}
            search_cols = [table.c.name]
            for fname in candidate_fields:
                if fname in seen:
                    continue
                col = table.c.get(fname)
                if col is not None:
                    search_cols.append(col)
                    seen.add(fname)
            filtered_q = filtered_q.where(or_(*(col.ilike(f"%{search}%") for col in search_cols)))

        # Controller hook: list_filter_extra - allows DocType controllers
        # (e.g. in app code) to inject extra WHERE clauses without touching
        # the framework core.
        if ctrl_cls.list_filter_extra is not Document.list_filter_extra:
            extra_clause = await ctrl_cls.list_filter_extra(session, filters, table)
            if extra_clause is not None:
                filtered_q = filtered_q.where(extra_clause)

        preserve_ancestors = True
        if ctrl_cls.tree_preserve_ancestors is not Document.tree_preserve_ancestors:
            preserve_ancestors = await ctrl_cls.tree_preserve_ancestors(session, filters, table)

        filtered_q = filtered_q.where(table.c.name.in_(tree_ids))
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

        return [r for r in all_rows if r["name"] in keep_ids]

    async def get_ancestors(
        self,
        session: AsyncSession,
        doctype: str,
        node_id: str,
        *,
        fields: list[str] | None = None,
        scope: Select | None = None,
    ) -> list[dict[str, Any]]:
        """Return ordered path from the direct parent up to the root.

        ``scope`` - a ``SELECT name`` of the nodes the caller may see; hidden
        ancestors are left out of the path.
        """
        import grunt

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype},
            )
        parent_field = _require_tree(dt)
        table = dt.table
        title_col = _title_field(dt)

        select_cols = self._build_select_cols(table, fields, title_col, parent_field)
        col_names = [c.key for c in select_cols]

        anchor = select(*select_cols, literal(0).label("_depth")).where(table.c.name == node_id)
        ancestors_cte = anchor.cte("ancestors", recursive=True)

        recursive_step = (
            select(*(table.c[c] for c in col_names), (ancestors_cte.c._depth + 1).label("_depth"))
            .join(ancestors_cte, table.c.name == ancestors_cte.c[parent_field])
            .where(
                ancestors_cte.c[parent_field].is_not(None),
                ancestors_cte.c[parent_field] != "",
            )
        )
        ancestors_cte = ancestors_cte.union_all(recursive_step)

        stmt = (
            select(*(ancestors_cte.c[c] for c in col_names))
            .where(ancestors_cte.c.name != node_id)
            .order_by(ancestors_cte.c._depth.desc())
        )
        if scope is not None:
            stmt = stmt.where(ancestors_cte.c.name.in_(scope))
        result = await session.execute(stmt)
        return [dict(r._mapping) for r in result.fetchall()]

    # Write

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
        from datetime import UTC, datetime

        from sqlalchemy import update as sa_update

        import grunt

        dt = await grunt.get_meta(doctype)
        if dt is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_("DocType “%(doctype)s” not found") % {"doctype": doctype},
            )
        parent_field = _require_tree(dt)
        table = dt.table

        # Cycle guard: get subtree ids of the node being moved
        if new_parent_id:
            subtree = await self.get_tree(session, doctype, root_id=node_id)
            subtree_ids = self._collect_ids(subtree)
            if new_parent_id in subtree_ids:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=_("Cannot move a node into its own subtree (cycle detected)"),
                )

        stmt = (
            sa_update(table)
            .where(table.c.name == node_id)
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
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_("Node not found"))

        log.info("tree.node_moved", doctype=doctype, node=node_id, new_parent=new_parent_id)
        return dict(row._mapping)

    # Helpers

    @staticmethod
    def _build_select_cols(
        table: Any,
        fields: list[str] | None,
        title_col: str,
        parent_field: str,
        *,
        sort_by: str | None = None,
    ) -> list:
        """Build SA column list: always include name + parent_field + title,
        then requested extras."""
        always = {"name", parent_field, title_col}
        if sort_by:
            always.add(sort_by)
        wanted = set(fields) if fields else {c.key for c in table.c}
        final = always | wanted
        return [table.c[c] for c in final if c in table.c]

    @staticmethod
    def _normalize_sort_order(raw: str | None) -> str:
        value = (raw or "asc").strip().lower()
        return "desc" if value == "desc" else "asc"

    async def _resolve_sort_config(
        self,
        session: AsyncSession,
        dt: Any,
        table: Any,
        filters: dict[str, Any],
        *,
        explicit_sort_by: str | None,
        explicit_sort_order: str | None,
        fallback_field: str,
        fallback_if_missing: bool,
        controller_cls: type,
    ) -> tuple[str | None, str]:
        from grunt.document.base import Document

        tree_view = dt.get_tree_view()
        default_sort_by = tree_view.sort_by if tree_view else None
        default_sort_order = tree_view.sort_order if tree_view else "asc"

        resolved_sort_by = explicit_sort_by or default_sort_by
        resolved_sort_order = self._normalize_sort_order(explicit_sort_order or default_sort_order)

        if resolved_sort_by is None and fallback_if_missing:
            resolved_sort_by = fallback_field

        if controller_cls.tree_get_sort_order is not Document.tree_get_sort_order:
            override = await controller_cls.tree_get_sort_order(
                session,
                filters,
                table,
                sort_by=resolved_sort_by,
                sort_order=resolved_sort_order,
            )
            if override:
                override_sort_by, override_sort_order = override
                if override_sort_by:
                    resolved_sort_by = override_sort_by
                resolved_sort_order = self._normalize_sort_order(override_sort_order)

        if resolved_sort_by and resolved_sort_by not in table.c:
            if fallback_if_missing and fallback_field in table.c:
                resolved_sort_by = fallback_field
            else:
                resolved_sort_by = None

        return resolved_sort_by, resolved_sort_order

    @staticmethod
    def _sort_flat_rows(
        rows: list[dict[str, Any]],
        sort_by: str,
        sort_order: str,
    ) -> list[dict[str, Any]]:
        present: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []

        for row in rows:
            if row.get(sort_by) is None:
                missing.append(row)
            else:
                present.append(row)

        def _key(row: dict[str, Any]) -> tuple[int, Any, str]:
            value = row.get(sort_by)
            if isinstance(value, (int, float)):
                return (0, value, str(row.get("name") or ""))
            return (0, str(value).casefold(), str(row.get("name") or ""))

        present_sorted = sorted(present, key=_key, reverse=(sort_order == "desc"))
        return [*present_sorted, *missing]

    async def _apply_tree_sort_children_hook(
        self,
        controller_cls: type,
        session: AsyncSession,
        nodes: list[dict[str, Any]],
        *,
        sort_by: str | None,
        sort_order: str,
    ) -> list[dict[str, Any]]:
        stack: list[tuple[dict[str, Any] | None, list[dict[str, Any]]]] = [(None, nodes)]
        while stack:
            parent, children = stack.pop()
            reordered = await controller_cls.tree_sort_children(
                session,
                children,
                parent=parent,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            if reordered is not children:
                children[:] = reordered
            for child in children:
                nested_children = child.get("children") or []
                if nested_children:
                    stack.append((child, nested_children))
        return nodes

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
        by_name: dict[str, dict[str, Any]] = {}
        for row in flat:
            row["children"] = []
            by_name[row["name"]] = row

        roots: list[dict[str, Any]] = []
        for row in flat:
            pid = row.get(parent_field)
            if pid:
                parent = by_name.get(pid)
                if parent and parent["name"] != row["name"]:
                    parent["children"].append(row)
                    continue
            roots.append(row)
        return roots

    @staticmethod
    def _collect_ids(nodes: list[dict[str, Any]]) -> set[str]:
        """Recursively collect all ``name`` values from a nested tree."""
        ids: set[str] = set()
        stack = list(nodes)
        while stack:
            n = stack.pop()
            ids.add(n["name"])
            stack.extend(n.get("children") or [])
        return ids


tree_service = TreeService()
