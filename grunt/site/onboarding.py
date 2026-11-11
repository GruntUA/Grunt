"""Module onboarding - "first steps" checklists (``ModuleOnboarding``).

A step is done when the fact it asks for is true, checked on every read:
Create Entry - someone created a record of the DocType (the user, for a
per-user checklist; records the system seeded don't count); Update Settings -
the singleton's field is set to something other than its default (or equals
``value_to_validate``); Take a Tour - the ``FormTour`` has been taken. The
other actions only lead somewhere, so they count once opened. Done-by-hand,
skipped steps and hidden checklists are ``OnboardingProgress`` rows - with an
empty ``user`` for a site checklist; so are the tours a user has taken.
"""

import copy
from typing import Any

from grunt.api.context import whitelist
from grunt.api.v1.dashboard import page_visible
from grunt.auth.constants import SYSTEM_USER_EMAIL
from grunt.auth.current import acting_user
from grunt.db.api import GruntDB
from grunt.errors import throw
from grunt.i18n import _
from grunt.i18n.meta import translate_record
from grunt.local import require_session, system_context
from grunt.metadata.registry import doctype_registry
lazy from grunt.document.api import documents

_db = GruntDB()  # stateless: reads through the context's session

AUTO_ACTIONS = ("Create Entry", "Update Settings", "Take a Tour")
TOUR_VIEWS = ("Form", "List")  # FormTour.view - where a tour runs
TOUR_FIELDS = ["reference_doctype", "view"]
_MARKS = ("Completed", "Skipped")


# Everything below reads under ``system_context`` (progress rows are not the
# user's to read directly), where ``acting_user()`` is the system user - so
# the caller's user is taken first and passed along.


def _scope_user(onboarding: dict[str, Any], user: str) -> str:
    return user if onboarding.get("progress_scope") == "User" else ""


async def _progress(onboarding: dict[str, Any], user: str) -> tuple[dict[str, str], bool]:
    """``({step_id: status}, hidden)`` for *user*."""
    me = user
    rows = await _db.get_all(
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
    if step.get("action") == "Take a Tour":
        taken = {"form_tour": step.get("form_tour") or "", "status": "Completed"}
        return (
            await _db.count("OnboardingProgress", {**taken, **({"user": user} if user else {})}) > 0
        )
    doctype = step.get("reference_doctype") or ""
    meta = await doctype_registry.get_meta(doctype) if doctype else None
    if meta is None:
        return False
    if step.get("action") == "Create Entry":
        owner = {"owner": user} if user else {"owner__ne": SYSTEM_USER_EMAIL}
        return await _db.count(doctype, owner) > 0
    fieldname = step.get("field") or ""
    rows = await _db.get_all(doctype, fields=None, limit=1)
    value = rows[0].get(fieldname) if rows else None
    expected = (step.get("value_to_validate") or "").strip()
    if expected in ("", "%"):
        field = meta.get_field(fieldname)
        default = field.default if field else None
        return value not in (None, "", 0, False, []) and str(value) != str(default)
    return str(value) == expected


async def _target(step: dict[str, Any]) -> dict[str, Any] | None:
    """Where the step's button leads - an ``appUrl`` link for the desk."""
    action = step.get("action")
    if action == "Take a Tour":
        tour = step.get("form_tour") or ""
        row = await _db.get_value("FormTour", tour, ["reference_doctype", "view"], as_dict=True)
        doctype = (row or {}).get("reference_doctype")
        meta = await doctype_registry.get_meta(doctype) if doctype else None
        if meta is None:
            return None
        target = {"type": "DocType", "name": doctype, "query": {"tour": tour}}
        on_list = (row or {}).get("view") == "List"
        return target if on_list or meta.doc.is_singleton else {**target, "id": "new"}
    if action == "Create Entry":
        return {"type": "DocType", "name": step.get("reference_doctype"), "id": "new"}
    if action == "Update Settings" or (step.get("reference_doctype") and not step.get("route")):
        return {"type": "DocType", "name": step.get("reference_doctype")}
    if action == "View Report":
        return {"type": "Report", "name": step.get("report")}
    if step.get("route"):
        return {"type": "URL", "name": step["route"]}
    return None


async def _visible(app: str | None, roles: list[str]) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {"is_published": True}
    if app:
        filters["app"] = app
    rows = await _db.get_all(
        "ModuleOnboarding", filters=filters, fields=["name"], order_by="name", limit=None
    )
    docs = [await documents.get_doc("ModuleOnboarding", r["name"]) for r in rows]
    return [d for d in docs if page_visible({**d, "is_published": True}, roles)]


async def _summary(onboarding: dict[str, Any], user: str) -> dict[str, Any] | None:
    marks, hidden = await _progress(onboarding, user)
    if hidden:
        return None
    onboarding = await translate_record(copy.deepcopy(onboarding))
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
                "target": await _target(step),
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


@whitelist()
async def get_onboardings(app: str | None = None) -> list[dict[str, Any]]:
    """Checklists the user sees (all, or *app*'s), with each step's status."""
    user = acting_user()
    async with system_context(require_session()):
        out = [await _summary(o, user.email) for o in await _visible(app or None, user.role_names)]
    return [o for o in out if o and o["total"]]


async def _require(onboarding: str, roles: list[str]) -> dict[str, Any]:
    async with system_context(require_session()):
        for o in await _visible(None, roles):
            if o["name"] == onboarding:
                return o
    throw(_("Onboarding not found"), "NOT_FOUND")


async def _set(key: dict[str, str], status: str | None) -> None:
    async with system_context(require_session()):
        for name in await _db.get_all("OnboardingProgress", filters=key, pluck="name"):
            await documents.delete_doc("OnboardingProgress", name)
        if status:
            await documents.new_doc("OnboardingProgress", {**key, "status": status})


@whitelist()
async def mark_step(onboarding: str, step_id: str, status: str = "Completed") -> dict[str, Any]:
    """Mark a step Completed or Skipped, or ``Pending`` to take the mark back."""
    user = acting_user()
    o = await _require(onboarding, user.role_names)
    if not any(s.get("step_id") == step_id for s in o.get("steps") or []):
        throw(_("Step not found"), "NOT_FOUND")
    if status not in (*_MARKS, "Pending"):
        throw(_("Unknown step status"))
    key = {"onboarding": onboarding, "step_id": step_id, "user": _scope_user(o, user.email)}
    await _set(key, None if status == "Pending" else status)
    async with system_context(require_session()):
        summary = await _summary(o, user.email)
    return summary or {}


@whitelist()
async def hide_onboarding(onboarding: str) -> None:
    """Hide the checklist for the current user."""
    user = acting_user()
    await _require(onboarding, user.role_names)
    await _set({"onboarding": onboarding, "step_id": "", "user": user.email}, "Hidden")


# Tours (FormTour) - the published ones of a form or a list whose roles fit
# the user; taking one is a ``Completed`` progress row of that user.


async def _tours(doctype: str, roles: list[str], view: str) -> list[dict[str, Any]]:
    names = await _db.get_all(
        "FormTour",
        filters={"is_published": True, "reference_doctype": doctype},
        pluck="name",
        order_by="name",
        limit=None,
    )
    docs = [await documents.get_doc("FormTour", n) for n in names]
    return [
        d
        for d in docs
        if (d.get("view") or "Form") == view and page_visible({**d, "is_published": True}, roles)
    ]


@whitelist()
async def get_form_tours(doctype: str, view: str = "Form") -> list[dict[str, Any]]:
    """Tours of *doctype*'s form (or list, ``view="List"``) the user sees, and
    whether they have taken each."""
    if view not in TOUR_VIEWS:
        throw(_("Unknown view: %(view)s") % {"view": view})
    user = acting_user()
    async with system_context(require_session()):
        tours = await _tours(doctype, user.role_names, view)
        taken = set(
            await _db.get_all(
                "OnboardingProgress",
                filters={"user": user.email, "form_tour__in": [t["name"] for t in tours]},
                pluck="form_tour",
                limit=None,
            )
            if tours
            else []
        )
        tours = [await translate_record(copy.deepcopy(t)) for t in tours]
    return [
        {
            "name": t["name"],
            "title": t.get("title"),
            "auto_start": bool(t.get("auto_start")),
            "taken": t["name"] in taken,
            "steps": [
                {
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "fieldname": s.get("fieldname") or None,
                    "element": s.get("element") or None,
                }
                for s in t.get("steps") or []
            ],
        }
        for t in tours
        if t.get("steps")
    ]


@whitelist()
async def complete_form_tour(tour: str) -> None:
    """Note that the user has taken *tour* (finished or closed it)."""
    user = acting_user()
    async with system_context(require_session()):
        row = await _db.get_value("FormTour", tour, ["reference_doctype", "view"], as_dict=True)
        doctype = (row or {}).get("reference_doctype")
        view = (row or {}).get("view") or "Form"
        visible = bool(doctype) and any(
            t["name"] == tour for t in await _tours(doctype, user.role_names, view)
        )
    if not visible:
        throw(_("Form tour not found"), "NOT_FOUND")
    await _set({"form_tour": tour, "step_id": "", "user": user.email}, "Completed")
