"""Notifications of a workflow transition (``WorkflowTransition.notify``).

Recipients, comma-separated in the transition's ``notify``:

* ``owner`` - the document's author;
* ``previous`` - who performed the previous workflow action on the document
  (e.g. the author who sent it for review, when a reviewer sends it back);
* ``next`` - users who can take the next step: they hold a role allowed on a
  button transition out of the new state *and* can read this very document
  (role permissions, ``match`` rules and User Permissions - so a section
  moderator hears only about their own sections).

The actor is never notified. A system notification (with web push) always;
an email too with ``notify_email``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt import _, log

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.workflow.engine import ActiveTransition


async def notify_transition(
    active: ActiveTransition, doc: dict[str, Any], user: User, *, previous: str | None = None
) -> None:
    tokens = set(active.transition.notify)
    if not tokens:
        return
    recipients: list[str] = []
    if "owner" in tokens and doc.get("owner"):
        recipients.append(doc["owner"])
    if "previous" in tokens and previous:
        recipients.append(previous)
    if "next" in tokens:
        recipients.extend(await next_actors(active.doctype, doc))
    recipients = [r for r in dict.fromkeys(recipients) if r and r != user.email]
    if not recipients:
        return

    from grunt.notification.service import notification_service

    meta = await grunt.get_meta(active.doctype)
    title = _doc_title(meta, doc)
    subject = f"{active.action}: {title}"
    message = await _message(active, user, meta)
    session = grunt.get_session()
    for recipient in recipients:
        try:
            await notification_service.notify(
                session,
                user=recipient,
                doctype=active.doctype,
                doc_id=active.doc_id,
                subject=subject,
                message=message,
                email=active.transition.notify_email,
            )
        except Exception:
            log.exception("workflow.notify_failed", recipient=recipient, doctype=active.doctype)


async def next_actors(doctype: str, doc: dict[str, Any]) -> list[str]:
    """Users who can take a button transition out of *doc*'s current state."""
    from grunt.auth.doctypes.User.user import get_user_by_id
    from grunt.permissions.rbac import permission_checker
    from grunt.permissions.user_permissions import doc_passes
    from grunt.workflow.engine import user_may_take
    from grunt.workflow.registry import get_active_workflow

    workflow = await get_active_workflow(doctype)
    if not workflow:
        return []
    state = doc.get(workflow.state_field)
    transitions = [t for t in workflow.transitions if t.from_state == state and not t.on_edit]
    roles = {r for t in transitions for r in t.allowed_roles}
    if not roles:
        return []

    meta = await grunt.get_meta(doctype)
    if meta is None:
        return []
    session = grunt.get_session()
    result: list[str] = []
    async with grunt.system_context(session):
        rows = await grunt.db.get_all(
            "UserRole",
            filters={"role_name__in": sorted(roles), "parent_doctype": "User"},
            fields=["parent_name"],
            limit=None,
        )
        # UserRole points at the account id; it may differ from the current
        # email (an account renamed later) - notifications go to the email.
        candidates = sorted({r["parent_name"] for r in rows})
        users = [await get_user_by_id(user_id) for user_id in candidates]
    for candidate in users:
        if candidate is None or not candidate.get("is_active", True):
            continue
        if not any(user_may_take(t, candidate) for t in transitions):
            continue
        if not await permission_checker.check(candidate, meta, "read", doc):
            continue
        if not await doc_passes(candidate, meta, doc):
            continue
        result.append(candidate.email)
    return result


async def previous_actor(doctype: str, doc_id: str) -> str | None:
    """Who performed the latest workflow action on the document (before the current one)."""
    session = grunt.get_session()
    async with grunt.system_context(session):
        rows = await grunt.db.get_all(
            "ActivityLog",
            filters={"doctype": doctype, "doc_id": doc_id, "action": "Workflow"},
            fields=["user"],
            order_by="created_at",
            order="desc",
            limit=1,
        )
    return rows[0]["user"] if rows else None


def _doc_title(meta: Any, doc: dict[str, Any]) -> str:
    field = meta.get_title_field()
    if field == "name" and meta.has_field("title"):
        field = "title"
    return str(doc.get(field) or doc.get("name") or "")


async def _message(active: ActiveTransition, user: User, meta: Any) -> str:
    who = user.get("full_name") or user.email
    lines = [
        _("%(user)s: “%(action)s” — %(from)s → %(to)s")
        % {
            "user": who,
            "action": active.action,
            "from": await _state_label(active.doctype, active.from_state),
            "to": await _state_label(active.doctype, active.to_state),
        }
    ]
    if active.comment:
        lines += ["", _("Comment:"), active.comment]
    if url := await _form_url(meta, active.doc_id):
        lines += ["", url]
    return "\n".join(lines)


async def _state_label(doctype: str, state: str | None) -> str:
    from grunt.workflow.registry import get_active_workflow

    workflow = await get_active_workflow(doctype)
    found = next((s for s in workflow.states if s.state == state), None) if workflow else None
    return (found.label if found and found.label else state) or "—"


async def _form_url(meta: Any, doc_id: str) -> str:
    """The document's form in the desk - absolute when the site is named by its domain."""
    from grunt.api.v1.meta import _get_app_name_for_module
    from grunt.site.manager import current_site

    app = await _get_app_name_for_module(meta.doc.module or "") or "grunt"
    site = current_site.get()
    base = f"https://{site}" if "." in site else ""
    return f"{base}/app/{app}/{meta.doc.name}/{doc_id}"
