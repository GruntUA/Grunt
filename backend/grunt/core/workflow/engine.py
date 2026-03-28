"""Workflow engine — state machine for DocType documents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt.core.metadata.doctype import DocType, WorkflowTransition, WorkflowState

if TYPE_CHECKING:
    from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()


class WorkflowEngine:
    async def get_state(self, doctype: DocType, doc: dict) -> WorkflowState | None:
        if not doctype.workflow:
            return None
        state_value = doc.get(doctype.workflow.state_field)
        return next(
            (s for s in doctype.workflow.states if s.name == state_value),
            None,
        )

    async def get_available_transitions(
        self,
        doctype: DocType,
        doc: dict,
        user: "GruntUser",
    ) -> list[WorkflowTransition]:
        if not doctype.workflow:
            return []
        current_state = await self.get_state(doctype, doc)
        current_state_name = current_state.name if current_state else None

        available: list[WorkflowTransition] = []
        for t in doctype.workflow.transitions:
            if t.from_state != current_state_name:
                continue
            # Check roles
            if t.allowed_roles:
                user_roles = set(getattr(user, "roles", []) or [])
                if not user_roles.intersection(set(t.allowed_roles)):
                    if not getattr(user, "is_superadmin", False):
                        continue
            # Check condition
            if t.condition:
                if not self._eval_condition(t.condition, doc, user.email):
                    continue
            available.append(t)
        return available

    async def apply_transition(
        self,
        doctype: DocType,
        doc_id: str,
        action: str,
        user: "GruntUser",
        session: AsyncSession,
        engine: AsyncEngine,
    ) -> dict:
        from grunt.core.metadata.compiler import get_table_name
        from sqlalchemy import select, update, Table, MetaData

        table_name = get_table_name(doctype.module, doctype.name)
        meta = MetaData()
        async with engine.connect() as conn:
            table = await conn.run_sync(
                lambda sync_conn: Table(table_name, meta, autoload_with=sync_conn)
            )

        # Get document
        async with engine.connect() as conn:
            result = await conn.execute(select(table).where(table.c.id == doc_id))
            row = result.mappings().first()

        if not row:
            raise HTTPException(status_code=404, detail="Документ не знайдено")

        doc = dict(row)
        available = await self.get_available_transitions(doctype, doc, user)
        transition = next((t for t in available if t.action == action), None)

        if not transition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Перехід недоступний",
            )

        # Apply
        state_field = doctype.workflow.state_field  # type: ignore[union-attr]
        now = datetime.now(timezone.utc)
        async with engine.begin() as conn:
            await conn.execute(
                update(table)
                .where(table.c.id == doc_id)
                .values({state_field: transition.to_state, "modified_at": now})
            )

        # Re-read updated document
        async with engine.connect() as conn:
            result = await conn.execute(select(table).where(table.c.id == doc_id))
            updated_doc = dict(result.mappings().first())  # type: ignore[arg-type]

        # Run controller after_save (so apps can react to state changes)
        from grunt.core.document.registry import document_registry  # noqa: PLC0415
        try:
            controller_cls = document_registry.get(doctype.name)
            controller = controller_cls(doctype.name, updated_doc, user, session)
            await controller.after_save()
        except Exception:  # noqa: BLE001
            logger.exception("workflow.controller_after_save_error", doctype=doctype.name)

        # Fire on_transition hooks
        from grunt.core.hooks import fire as fire_hook  # noqa: PLC0415
        try:
            await fire_hook(
                "on_transition",
                doctype=doctype.name,
                doc=updated_doc,
                from_state=doc.get(state_field),
                to_state=transition.to_state,
                action=action,
                user=user,
                session=session,
            )
        except Exception:  # noqa: BLE001
            logger.exception("hook.on_transition_error")

        # Fire after_save / after_update hooks (so doc_events work for transitions too)
        try:
            await fire_hook(
                "after_save",
                doctype=doctype.name,
                doc=updated_doc,
                user=user,
                session=session,
            )
        except Exception:  # noqa: BLE001
            logger.exception("hook.after_save_on_transition_error")

        # Log activity
        try:
            await self._log_activity(
                doctype=doctype.name,
                doc_id=doc_id,
                action="workflow_transition",
                user=user.email,
                details={
                    "from": doc.get(state_field),
                    "to": transition.to_state,
                    "action": action,
                },
                session=session,
            )
        except Exception:  # noqa: BLE001
            pass  # Non-critical

        # Broadcast WS
        try:
            from grunt.api.v1.ws import manager  # noqa: PLC0415

            await manager.broadcast_doc(
                doctype.name,
                doc_id,
                {
                    "event": "workflow_transition",
                    "data": {"action": action, "to_state": transition.to_state},
                },
            )
        except Exception:  # noqa: BLE001
            pass

        # Return updated doc (already read above)
        return updated_doc

    async def _log_activity(
        self,
        doctype: str,
        doc_id: str,
        action: str,
        user: str,
        details: dict,
        session: AsyncSession,
    ) -> None:
        import uuid  # noqa: PLC0415

        from grunt.core.db.system_tables import GruntLogActivity  # noqa: PLC0415

        entry = GruntLogActivity(
            id=str(uuid.uuid4()),
            doctype=doctype,
            doc_id=doc_id,
            action=action,
            user=user,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.commit()

    def _eval_condition(self, condition: str, doc: dict, user: str) -> bool:
        safe_globals: dict = {"__builtins__": {}, "now": datetime.now}
        safe_locals: dict = {"doc": doc, "user": user}
        try:
            result = eval(condition, safe_globals, safe_locals)  # noqa: S307
            return bool(result)
        except Exception:  # noqa: BLE001
            return True  # Don't block on error


workflow_engine = WorkflowEngine()
