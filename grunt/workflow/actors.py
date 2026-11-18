"""Who acts on a workflow document - for the recipients of transition notifications.

* :func:`previous_actor` - who performed the latest workflow action on the
  document (e.g. the author who sent it for review, when a reviewer sends it back);
* :func:`next_actors` - users who can take the next step: they hold a role
  allowed on a button transition out of the current state (the author not, on
  a ``deny_self_approval`` one) *and* can read this
  very document (role permissions, ``match`` rules and User Permissions - so a
  section moderator hears only about their own sections).

Used by the ``Previous actor`` / ``Next actors`` recipient rows of a
``Notification`` (:mod:`grunt.notification.rules`).
"""

from typing import Any

from grunt.db.api import GruntDB
from grunt.i18n import N_
from grunt.local import require_session, system_context
from grunt.metadata.registry import doctype_registry
from grunt.permissions.perms import ALL, user_perms
from grunt.workflow.transition import is_self_approval, user_may_take
lazy from grunt.permissions.access import RoleAccess
lazy from grunt.permissions.rbac import permission_checker
lazy from grunt.permissions.roles import role_holders
lazy from grunt.permissions.scopes import doc_in_scopes
lazy from grunt.workflow.registry import get_active_workflow

_db = GruntDB()  # stateless: reads through the context's session

# The text of a transition notification (migration 0024 writes it into the rules
# it makes; apps ship it in their standard rules) - marked here so the core's
# catalog keeps its translations.
TRANSITION_STRINGS = (N_("%(user)s: “%(action)s” — %(from)s → %(to)s"), N_("Comment:"))


async def next_actors(doctype: str, doc: dict[str, Any]) -> list[str]:
    """Users who can take a button transition out of *doc*'s current state."""

    workflow = await get_active_workflow(doctype)
    if not workflow:
        return []
    state = doc.get(workflow.state_field)
    transitions = [t for t in workflow.transitions if t.from_state == state and not t.on_edit]
    roles = {r for t in transitions for r in t.allowed_roles}
    if not roles:
        return []

    meta = await doctype_registry.get_meta(doctype)
    if meta is None:
        return []
    result: list[str] = []
    async with system_context(require_session()):
        holders = await role_holders(roles)
    for holder in holders:
        email = holder.get("email")
        if not email:
            continue
        # Roles that hold for this document - a scoped role only within its scope.
        access = RoleAccess(meta, email, [])
        held = [
            role
            for role, scopes in holder["roles"].items()
            if not scopes or await doc_in_scopes(access, scopes, doc)
        ]
        unrestricted = ALL in await user_perms(email)
        if not any(
            user_may_take(t, held, unrestricted=unrestricted)
            and not is_self_approval(t, doc, email)
            for t in transitions
        ):
            continue
        if not await permission_checker.check(meta, "read", doc, user=email):
            continue
        result.append(email)
    return result


async def previous_actor(doctype: str, doc_id: str) -> str | None:
    """Who performed the latest workflow action on the document (before the current one)."""
    session = require_session()
    async with system_context(session):
        rows = await _db.get_all(
            "ActivityLog",
            filters={"ref_doctype": doctype, "doc_id": doc_id, "action": "Workflow"},
            fields=["user"],
            order_by="created_at",
            order="desc",
            limit=1,
        )
    return rows[0]["user"] if rows else None


async def state_label(doctype: str, state: str | None) -> str:
    """The label a workflow state is shown with (its name when it has none)."""

    workflow = await get_active_workflow(doctype)
    found = next((s for s in workflow.states if s.state == state), None) if workflow else None
    return (found.label if found and found.label else state) or "—"
