"""Write-pipeline checks for DocTypes with an active workflow.

Called from grunt/document/mixins/write.py. Outside a transition (see
:func:`grunt.workflow.engine.current_transition`):

* the state field can't be set to anything but the initial state on create,
  and can't be changed on update - only transitions move it;
* an ``on_edit`` transition available to the user turns an edit into that
  transition (e.g. an edited published page goes back to review);
* otherwise a state's ``edit_roles`` decides who may edit or delete; a user
  whose edits are ``on_edit`` transitions can't delete in that state.

The internal system user (fixtures, imports, migrations) is exempt from all of it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

import grunt
from grunt import _
from grunt.errors import not_found

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User
    from grunt.workflow.engine import ActiveTransition

# Never compared when deciding whether an edit changed the document.
_SYSTEM_FIELDS = frozenset(
    {"name", "owner", "created_at", "modified_at", "modified_by", "idx"}
)


def _exempt(user: User) -> bool:
    from grunt.auth.doctypes.User.user import SYSTEM_USER
    from grunt.workflow.engine import current_transition

    return current_transition() is not None or user.email == SYSTEM_USER.email


def _norm(value: Any) -> str:
    """Comparable form of a field value as the DB returns it or a form sends it back."""
    from datetime import date, datetime

    if value is None:
        return ""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, datetime):
        value = value.replace(tzinfo=None).isoformat()
    elif isinstance(value, date):
        value = value.isoformat()
    text = str(value).strip()
    # "2026-03-15 09:44:00+00:00" / "...T09:44:00Z" / "...T09:44:00.000" -> one shape.
    if len(text) >= 19 and text[4] == "-" and text[10] in " T" and text[13] == ":":
        text = text[:10] + "T" + text[11:19]
    return text


def _same(a: Any, b: Any) -> bool:
    return _norm(a) == _norm(b)


def _label(workflow: Any, state: str | None) -> str:
    found = next((s for s in workflow.states if s.state == state), None)
    return (found.label if found and found.label else state) or ""


async def check_create(doctype: str, data: dict[str, Any], user: User | None) -> None:
    """A new document starts in the initial state - no other state on create."""
    from grunt.workflow.registry import get_active_workflow

    workflow = await get_active_workflow(doctype)
    if not workflow or user is None or _exempt(user):
        return
    value = data.get(workflow.state_field)
    initial = next((s.state for s in workflow.states if s.is_initial), None)
    if value not in (None, "") and initial is not None and not _same(value, initial):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("A new document starts in the “%(state)s” state")
            % {"state": _label(workflow, initial)},
        )


async def check_update(
    doctype: str, existing: dict[str, Any], data: dict[str, Any], user: User | None
) -> ActiveTransition | None:
    """Validate an edit; returns the ``on_edit`` transition it turned into, if any.

    For an ``on_edit`` transition, *data* gets the new state (and its
    ``update_field``) - the caller saves it as part of the same update.
    """
    from grunt.workflow.engine import ActiveTransition, state_updates, workflow_engine
    from grunt.workflow.registry import get_active_workflow

    workflow = await get_active_workflow(doctype)
    if not workflow or user is None or _exempt(user):
        return None
    field = workflow.state_field
    state = existing.get(field)
    if field in data and not _same(data[field], state):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("The state changes only through workflow actions"),
        )

    changed = any(
        key in existing
        and key not in _SYSTEM_FIELDS
        and key != field
        and not _same(value, existing[key])
        for key, value in data.items()
    )
    if changed:
        meta = await _meta(doctype)
        auto = await workflow_engine.get_available_transitions(meta, existing, user, on_edit=True)
        if auto:
            transition = auto[0]
            data.update(state_updates(workflow, transition.to_state))
            return ActiveTransition(
                doctype=doctype,
                doc_id=existing["name"],
                from_state=state,
                to_state=transition.to_state,
                action=transition.action,
                transition=transition,
            )
    _check_edit_roles(workflow, state, user)
    return None


async def check_delete(doctype: str, existing: dict[str, Any], user: User | None) -> None:
    """``edit_roles`` govern deletion too; so does ``on_edit`` - whose edits go
    to review can't remove the document without it either."""
    from grunt.workflow.engine import workflow_engine
    from grunt.workflow.registry import get_active_workflow

    workflow = await get_active_workflow(doctype)
    if not workflow or user is None or _exempt(user):
        return
    state = existing.get(workflow.state_field)
    _check_edit_roles(workflow, state, user)
    meta = await _meta(doctype)
    if await workflow_engine.get_available_transitions(meta, existing, user, on_edit=True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_("In the “%(state)s” state the document can't be deleted")
            % {"state": _label(workflow, state)},
        )


def _check_edit_roles(workflow: Any, state: str | None, user: User | None) -> None:
    found = next((s for s in workflow.states if s.state == state), None)
    if not found or not found.edit_roles:
        return
    roles = set(getattr(user, "roles", []) or [])
    if roles.intersection(found.edit_roles) or "System Manager" in roles:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_("In the “%(state)s” state the document can't be edited")
        % {"state": _label(workflow, state)},
    )


async def _meta(doctype: str) -> Any:
    meta = await grunt.get_meta(doctype)
    if meta is None:
        raise not_found(_("DocType “%(doctype)s” not found") % {"doctype": doctype})
    return meta.doc
