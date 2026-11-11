"""The framework's own parts in the document write pipeline (:mod:`grunt.document.pipeline`).

Workflow guards and transitions, web-page routes, outgoing webhooks, the
activity feed and realtime progress - subsystems above the document layer.
The pipeline imports this module by path before the first write; the document
layer itself imports none of them.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from grunt.activity import record_activity
from grunt.activity.follow import notify_followers_of_update
from grunt.api.v1.ws import manager
from grunt.document.pipeline import UpdateScope, WriteExtension, register
from grunt.local import rebound
from grunt.log import log
from grunt.webhook.service import webhook_service
from grunt.website.generator import fill_route
from grunt.workflow.engine import workflow_engine
from grunt.workflow.guard import check_create, check_delete, check_update, is_exempt
from grunt.workflow.registry import get_active_workflow
from grunt.workflow.transition import ActiveTransition, _active


class _TransitionScope(UpdateScope):
    """An edit that is itself an ``on_edit`` transition: active while it is
    stored, finished (log, comment, notifications) after."""

    def __init__(self, transition: ActiveTransition) -> None:
        self._transition = transition

    @contextmanager
    def active(self) -> Iterator[None]:
        token = _active.set(self._transition)
        try:
            yield
        finally:
            _active.reset(token)

    async def finish(self, result: dict[str, Any], user: str, session: Any) -> None:
        await workflow_engine.finish_transition(self._transition, result, user, session)


class WorkflowExtension(WriteExtension):
    """The state moves only by transitions; ``edit_roles`` govern edits and deletes."""

    name = "workflow"

    async def prepare_insert(
        self, dt: Any, data: dict[str, Any], row: dict[str, Any], user: str
    ) -> None:
        workflow = await get_active_workflow(dt.name)
        if not workflow:
            return
        await check_create(dt.name, data, user)
        sf = workflow.state_field
        if sf in data:
            row[sf] = data[sf]
        initial = next((s for s in workflow.states if s.is_initial), None)
        if initial and row.get(sf) in (None, "", initial.state):
            row[sf] = initial.state
            # The state's update_field belongs to the workflow like the state
            # itself: a duplicated published page must not stay published.
            target = dt.get_field(initial.update_field or "")
            if target is not None and (target.fieldname not in data or not is_exempt(user)):
                row[target.fieldname] = target.coerce(initial.update_value)

    async def begin_update(
        self, doctype: str, existing: dict[str, Any], data: dict[str, Any], user: str
    ) -> UpdateScope | None:
        transition = await check_update(doctype, existing, data, user)
        return _TransitionScope(transition) if transition else None

    async def check_delete(self, doctype: str, existing: dict[str, Any], user: str) -> None:
        await check_delete(doctype, existing, user)


class WebsiteExtension(WriteExtension):
    """A web-view document gets a route slug of its title."""

    name = "website"

    async def before_store(self, dt: Any, row: dict[str, Any], session: Any) -> None:
        await fill_route(dt, row, session)


class WebhookExtension(WriteExtension):
    """Outgoing webhooks after a document is written."""

    name = "webhooks"

    async def after_write(
        self, event: str, session: Any, doctype: str, row: dict[str, Any]
    ) -> None:
        await webhook_service.fire(session, event, doctype, row)


class ActivityExtension(WriteExtension):
    """The activity feed and followers learn which fields an update changed."""

    name = "activity"

    async def changes_recorded(
        self,
        *,
        session: Any,
        engine: Any,
        doctype: str,
        doc_id: str,
        dt: Any,
        changed_fields: list[str],
        user: str,
    ) -> None:
        try:
            with rebound(session, engine):
                await record_activity(
                    doctype,
                    doc_id,
                    "Update",
                    user_email=user,
                    details={"changed_fields": changed_fields} if changed_fields else None,
                )
        except Exception:
            log.warning("activity_log.update_failed", doctype=doctype, doc_id=doc_id)
        try:
            await notify_followers_of_update(
                session=session,
                doctype=doctype,
                doc_id=doc_id,
                dt=dt,
                changed_fields=changed_fields,
                actor_email=user,
            )
        except Exception:
            log.exception("follow.update_notify_failed", doctype=doctype, doc_id=doc_id)


class RealtimeExtension(WriteExtension):
    """Progress of a long-running document goes to its open forms."""

    name = "realtime"

    async def doc_progress(self, doctype: str, doc_id: str, payload: dict[str, Any]) -> None:
        await manager.broadcast_doc(doctype, doc_id, "import_progress", payload)


for _extension in (
    WorkflowExtension(),
    WebsiteExtension(),
    WebhookExtension(),
    ActivityExtension(),
    RealtimeExtension(),
):
    register(_extension)
