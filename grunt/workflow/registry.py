"""Resolves the active ``Workflow`` document for a target DocType.

``Workflow`` is a regular DocType (see ``grunt/metadata/doctypes/Workflow``):
its documents live in the DB like any other document, with ``document_type``
pointing at the DocType it governs. This module hides that lookup behind a
small in-memory cache so ``workflow/engine.py`` and the write pipeline don't
hit the DB on every read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from grunt.hooks import on_doc
from grunt.i18n import _
from grunt.metadata.doctype import WorkflowState, WorkflowTransition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ResolvedWorkflow:
    """The active ``Workflow`` document for one target DocType, with children resolved."""

    def __init__(
        self,
        name: str,
        document_type: str,
        state_field: str,
        states: list[WorkflowState],
        transitions: list[WorkflowTransition],
    ) -> None:
        self.name = name
        self.document_type = document_type
        self.state_field = state_field
        self.states = states
        self.transitions = transitions


# document_type -> resolved workflow, or None if it has no active workflow.
_CACHE: dict[str, ResolvedWorkflow | None] = {}


def invalidate(document_type: str) -> None:
    """Drop the cached resolution for *document_type*, if any."""
    _CACHE.pop(document_type, None)


def clear_cache() -> None:
    """Drop all cached resolutions — used by tests."""
    _CACHE.clear()


# Registered here (not a separate grunt/workflow/hooks.py) so importing this
# module — which every call site already does — is enough to wire up cache
# invalidation. A hook file that nothing imports never registers itself.
@on_doc("Workflow", "after_save")
async def _invalidate_on_save(doc: dict, **kwargs: object) -> None:
    document_type = doc.get("document_type")
    if document_type:
        invalidate(document_type)


@on_doc("Workflow", "after_delete")
async def _invalidate_on_delete(doc: dict, **kwargs: object) -> None:
    document_type = doc.get("document_type")
    if document_type:
        invalidate(document_type)


async def _get_session() -> AsyncSession | None:
    """Return the ambient request/test session, falling back to the active site's.

    Mirrors ``DocTypeRegistry._lazy_load``'s session resolution: prefer whatever
    session ``grunt.context()`` already has bound (correct even when more than
    one site's DB is reachable from the same process), and only fall back to
    ``site_manager`` when nothing is bound (background tasks/schedulers).
    """
    from grunt.local import _session_ctx

    session = _session_ctx.get()
    if session is not None:
        return session

    from grunt.site.manager import site_manager

    try:
        site_name = site_manager.get_active_site()
        maker = site_manager.get_session_maker(site_name)
    except Exception:
        return None

    async with maker() as session:
        return session


async def get_active_workflow(document_type: str) -> ResolvedWorkflow | None:
    """Return the active ``Workflow`` for *document_type*, cached in memory."""
    if document_type in _CACHE:
        return _CACHE[document_type]

    import grunt
    from grunt.document.relations import _load_child_tables
    from grunt.document.serde import serialize_datetimes

    session = await _get_session()
    if session is None:
        # No session available at all (e.g. a disconnected background task) —
        # don't cache a negative result, so a later call with a real session
        # can still resolve it.
        return None

    meta = await grunt.get_meta("Workflow")
    if meta is None:
        from grunt.errors import not_found

        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": "Workflow"})
    dt = meta.doc  # _load_child_tables below is typed to take the raw DocType
    table = meta.table
    data_fields = {f.fieldname for f in meta.get_physical_fields()}
    cols = [c for c in table.c if c.key in data_fields or c.key == "name"]

    result = await session.execute(
        select(*cols)
        .where(table.c.document_type == document_type)
        .where(table.c.is_active.is_(True))
        .limit(1)
    )
    row = result.mappings().one_or_none()
    if row is None:
        _CACHE[document_type] = None
        return None

    doc = dict(row)
    serialize_datetimes(doc)
    await _load_child_tables(session, dt, doc)

    resolved = ResolvedWorkflow(
        name=doc["name"],
        document_type=document_type,
        state_field=doc.get("workflow_state_field") or "status",
        states=[WorkflowState.model_validate(s) for s in doc.get("states", [])],
        transitions=[WorkflowTransition.model_validate(t) for t in doc.get("transitions", [])],
    )
    _CACHE[document_type] = resolved
    return resolved
