"""Awaiting my action - workflow documents the user can move on now.

The "inbox" of the home page (``get_my_work``): for every active workflow, the
documents in a state with a button transition the user can take. Computed
from the transitions and permissions, with no table of its own (Frappe keeps
a ``Workflow Action`` row per document and user):

* only transitions with ``allowed_roles`` count, and only a role the user
  actually holds - a System Manager is not flooded with every document on
  the site, the same rule as the "Next actors" recipients;
* a scoped role counts only for the documents in its scope, the user must be
  able to read the document, and their own document on a
  ``deny_self_approval`` transition is not awaiting them
  (:func:`grunt.workflow.actors.may_act`);
* ``condition`` is not checked - a transition waiting for a field to be
  filled (e.g. "mark as done" after the execution note) is still work for
  this user.
"""

from typing import Any

from grunt.db.api import GruntDB
from grunt.i18n import _
from grunt.local import require_session, system_context
from grunt.log import log
from grunt.metadata.registry import doctype_registry
from grunt.permissions.roles import role_holders
from grunt.workflow.actors import may_act, stored_owner
from grunt.workflow.registry import get_active_workflow
lazy from grunt.document.api import documents
lazy from grunt.document.titles import resolve_reference_titles

_db = GruntDB()  # stateless: reads through the context's session

# Per workflow DocType: how many documents are looked at (newest first).
_PER_DOCTYPE = 100


async def awaiting_actions(email: str, limit: int = 50) -> list[dict[str, Any]]:
    """Documents *email* - the user of the current context, whose read rules
    the lists go through - can move on now, newest first, at most *limit*.

    Each item: ``doctype``, ``doctype_label``, ``name``, ``title``, ``state``, ``state_label``,
    ``color``, ``actions`` (button labels) and ``modified_at``.
    """
    session = require_session()
    async with system_context(session):
        doctypes = await _db.get_all(
            "Workflow", filters={"is_active": True}, pluck="document_type", limit=None
        )

    items: list[dict[str, Any]] = []
    for doctype in sorted({d for d in doctypes if d}):
        try:
            # A savepoint: a failed query here must not abort the request's transaction.
            async with session.begin_nested():
                items.extend(await _awaiting_in(doctype, email))
        except Exception:
            # No read access to the DocType, a broken workflow - the rest still shows.
            log.warning("workflow.inbox_skipped", doctype=doctype, user=email)

    items.sort(key=lambda i: str(i.get("modified_at") or ""), reverse=True)
    items = items[:limit]
    titles = await resolve_reference_titles([(i["doctype"], i["name"]) for i in items])
    for item in items:
        item["title"] = titles.get((item["doctype"], item["name"])) or item["name"]
    return items


async def _awaiting_in(doctype: str, email: str) -> list[dict[str, Any]]:
    workflow = await get_active_workflow(doctype)
    meta = await doctype_registry.get_meta(doctype)
    if workflow is None or meta is None:
        return []
    buttons = [t for t in workflow.transitions if not t.on_edit and t.allowed_roles]
    roles = {r for t in buttons for r in t.allowed_roles}
    if not roles:
        return []
    async with system_context(require_session()):
        mine = next((h for h in await role_holders(roles) if h.get("email") == email), None)
    if mine is None:
        return []
    held = set(mine["roles"])
    states = sorted({t.from_state for t in buttons if held.intersection(t.allowed_roles)})
    if not states:
        return []

    # The user's own read rules apply (scopes, match, shares).
    docs = await documents.get_list(
        doctype,
        filters={f"{workflow.state_field}__in": states},
        limit=_PER_DOCTYPE,
        order_by="modified_at",
        order="desc",
        include_total=False,
    )
    state_info = {s.state: s for s in workflow.states}
    out: list[dict[str, Any]] = []
    for doc in docs:
        state = doc.get(workflow.state_field)
        # Transitions out of this state on a role the user holds; may_act then
        # checks the role's scope, self-approval and read access per document.
        here = [t for t in buttons if t.from_state == state and held.intersection(t.allowed_roles)]
        # The stored owner: the list masks fields the user may not see.
        owner = await stored_owner(doctype, doc, here)
        actions = [
            t.action
            for t in here
            if await may_act(meta, email, mine["roles"], [t], doc, owner=owner, by_role_only=True)
        ]
        if not actions:
            continue
        info = state_info.get(state)
        out.append(
            {
                "doctype": doctype,
                "doctype_label": _(meta.doc.label or doctype),
                "name": doc["name"],
                "state": state,
                "state_label": (info.label if info and info.label else state),
                "color": info.color if info else "gray",
                "actions": actions,
                "modified_at": doc.get("modified_at"),
            }
        )
    return out
