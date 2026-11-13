"""The transition being applied, and who may take a transition.

The engine (grunt/workflow/engine.py) sets :func:`current_transition` while it
saves; the guard, notifications and controllers read it. Kept apart from the
engine so these readers do not depend on it.
"""

from collections.abc import Collection
from contextvars import ContextVar
from dataclasses import dataclass

lazy from grunt.metadata.doctype import WorkflowTransition


@dataclass(frozen=True, slots=True)
class ActiveTransition:
    """The transition being applied - visible to controllers via :func:`current_transition`."""

    doctype: str
    doc_id: str
    from_state: str | None
    to_state: str
    action: str
    transition: WorkflowTransition
    comment: str | None = None


_active: ContextVar[ActiveTransition | None] = ContextVar("grunt_workflow_transition", default=None)


def current_transition() -> ActiveTransition | None:
    """The workflow transition being saved right now, if any.

    Set while the update pipeline runs for a transition (a button or an
    ``on_edit`` transition), so ``validate``/``after_save`` can react to it::

        if (t := current_transition()) and t.to_state == "Approved": ...
    """
    return _active.get()


def user_may_take(
    transition: WorkflowTransition, roles: Collection[str], *, unrestricted: bool = False
) -> bool:
    """Role check of a transition for a user holding *roles*; *unrestricted* - the
    user holds every permission (``*``, System Manager) and may take any."""
    if unrestricted or not transition.allowed_roles:
        return True
    return bool(set(roles).intersection(transition.allowed_roles))
