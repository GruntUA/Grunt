"""Module onboarding - "first steps" checklists (``ModuleOnboarding``).

A step is done when the fact it asks for is true, checked on every read:
Create Entry - a record of the DocType exists (the user's own, for a per-user
checklist); Update Settings - the singleton's field is filled in (or equals
``value_to_validate``). The other actions only lead somewhere, so they count
once opened. Done-by-hand, skipped steps and hidden checklists are
``OnboardingProgress`` rows - with an empty ``user`` for a site checklist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grunt
from grunt import _
from grunt.api.v1.dashboard import page_visible

if TYPE_CHECKING:
    from grunt.auth.doctypes.User.user import User

AUTO_ACTIONS = ("Create Entry", "Update Settings")
_MARKS = ("Completed", "Skipped")


# Everything below reads under ``system_context`` (progress rows are not the
# user's to read directly), where ``grunt.get_user()`` is the system user - so
# the caller's user is taken first and passed along.


def _scope_user(onboarding: dict[str, Any], user: User) -> str:
    return user.email if onboarding.get("progress_scope") == "User" else ""


async def _progress(onboarding: dict[str, Any], user: User) -> tuple[dict[str, str], bool]:
    """``({step_id: status}, hidden)`` for *user*."""
    me = user.email
    rows = await grunt.db.get_all(
        "OnboardingProgress",
        filters={
            "onboarding": onboarding["name"],
            "user__in": list({me, _scope_user(onboarding, user)}),
        },
        fields=["step_id", "user", "status"],
        limit=None,
    )
    hidden = any(r["status"] == "Hidden" and r["user"] == me for r in rows)
    marks = {
        r["step_id"]: r["status"]
        for r in rows
        if r["step_id"] and r["status"] in _MARKS and r["user"] == _scope_user(onboarding, user)
    }
    return marks, hidden


async def _fact(step: dict[str, Any], user: str) -> bool:
    """Whether an auto step's condition holds right now."""
    doctype = step.get("reference_doctype") or ""
    if not doctype or await grunt.get_meta(doctype) is None:
        return False
    if step.get("action") == "Create Entry":
        return await grunt.db.count(doctype, {"owner": user} if user else None) > 0
    rows = await grunt.db.get_all(doctype, fields=None, limit=1)
    value = rows[0].get(step.get("field") or "") if rows else None
    expected = (step.get("value_to_validate") or "").strip()
    if expected in ("", "%"):
        return value not in (None, "", 0, False, [])
    return str(value) == expected


def _target(step: dict[str, Any]) -> dict[str, Any] | None:
    """Where the step's button leads - an ``appUrl`` link for the desk."""
    action = step.get("action")
    if action == "Create Entry":
        return {"type": "DocType", "name": step.get("reference_doctype"), "id": "new"}
    if action == "Update Settings":
        return {"type": "DocType", "name": step.get("reference_doctype")}
    if action == "View Report":
        return {"type": "Report", "name": step.get("report")}
    if step.get("route"):
        return {"type": "URL", "name": step["route"]}
    return None


async def _visible(app: str | None, user: User) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"is_published": True}
    if app:
        filters["app"] = app
    rows = await grunt.db.get_all(
        "ModuleOnboarding", filters=filters, fields=["name"], order_by="name", limit=None
    )
    docs = [await grunt.get_doc("ModuleOnboarding", r["name"]) for r in rows]
    return [d for d in docs if page_visible({**d, "is_published": True}, user)]


async def _summary(onboarding: dict[str, Any], user: User) -> dict[str, Any] | None:
    marks, hidden = await _progress(onboarding, user)
    if hidden:
        return None
    owner = _scope_user(onboarding, user)
    steps = []
    for step in onboarding.get("steps") or []:
        sid = step.get("step_id") or ""
        done = step.get("action") in AUTO_ACTIONS and await _fact(step, owner)
        status = "Completed" if done else marks.get(sid, "Pending")
        steps.append(
            {
                "step_id": sid,
                "title": step.get("title"),
                "description": step.get("description"),
                "action": step.get("action"),
                "action_label": step.get("action_label"),
                "target": _target(step),
                "status": status,
            }
        )
    return {
        "name": onboarding["name"],
        "title": onboarding.get("title"),
        "subtitle": onboarding.get("subtitle"),
        "app": onboarding.get("app"),
        "success_message": onboarding.get("success_message"),
        "documentation_url": onboarding.get("documentation_url"),
        "steps": steps,
        "done": sum(s["status"] != "Pending" for s in steps),
        "total": len(steps),
    }


@grunt.whitelist()
async def get_onboardings(app: str | None = None) -> list[dict[str, Any]]:
    """Checklists the user sees (all, or *app*'s), with each step's status."""
    user = grunt.get_user()
    async with grunt.system_context(grunt.get_session()):
        out = [await _summary(o, user) for o in await _visible(app or None, user)]
    return [o for o in out if o and o["total"]]


async def _require(onboarding: str, user: User) -> dict[str, Any]:
    async with grunt.system_context(grunt.get_session()):
        for o in await _visible(None, user):
            if o["name"] == onboarding:
                return o
    grunt.throw(_("Onboarding not found"), "NOT_FOUND")


async def _set(onboarding: str, step_id: str, user: str, status: str | None) -> None:
    key = {"onboarding": onboarding, "step_id": step_id, "user": user}
    async with grunt.system_context(grunt.get_session()):
        for name in await grunt.db.get_all("OnboardingProgress", filters=key, pluck="name"):
            await grunt.delete_doc("OnboardingProgress", name)
        if status:
            await grunt.new_doc("OnboardingProgress", {**key, "status": status})


@grunt.whitelist()
async def mark_step(onboarding: str, step_id: str, status: str = "Completed") -> dict[str, Any]:
    """Mark a step Completed or Skipped, or ``Pending`` to take the mark back."""
    user = grunt.get_user()
    o = await _require(onboarding, user)
    if not any(s.get("step_id") == step_id for s in o.get("steps") or []):
        grunt.throw(_("Step not found"), "NOT_FOUND")
    if status not in (*_MARKS, "Pending"):
        grunt.throw(_("Unknown step status"))
    await _set(onboarding, step_id, _scope_user(o, user), None if status == "Pending" else status)
    async with grunt.system_context(grunt.get_session()):
        summary = await _summary(o, user)
    return summary or {}


@grunt.whitelist()
async def hide_onboarding(onboarding: str) -> None:
    """Hide the checklist for the current user."""
    user = grunt.get_user()
    await _require(onboarding, user)
    await _set(onboarding, "", user.email, "Hidden")
