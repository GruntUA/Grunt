"""MilestoneTracker controller - validates the tracked field and seeds history.

The recording itself lives in :mod:`grunt.activity.milestones`.
"""

from __future__ import annotations

import grunt
from grunt import _
from grunt.activity import milestones
from grunt.document.base import Document


class MilestoneTracker(Document):
    """DocType controller for MilestoneTracker."""

    ref_doctype: str
    track_field: str

    _starts: bool = False

    async def validate(self) -> None:
        meta = await grunt.get_meta(self.ref_doctype)
        if meta is None:
            grunt.throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )
        dt = meta.doc
        if dt.is_child or dt.is_singleton or dt.is_virtual:
            grunt.throw(
                _("Milestones cannot be tracked on “%(doctype)s”") % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )

        field = (self.get("track_field") or "").strip() or (dt.status_field or "")
        if not field:
            grunt.throw(
                _("%(doctype)s has no status field - choose the field to track")
                % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )
        fdef = meta.get_field(field)
        if fdef is None or not fdef.is_physical or fdef.fieldtype == "Table":
            grunt.throw(
                _("“%(field)s” is not a field of %(doctype)s that can be tracked")
                % {"field": field, "doctype": dt.name},
                "VALIDATION_ERROR",
            )
        self.track_field = field

        duplicate = await grunt.db.exists(
            "MilestoneTracker",
            {"ref_doctype": dt.name, "track_field": field, "name__ne": self.id or ""},
        )
        if duplicate:
            grunt.throw(
                _("%(doctype)s.%(field)s is already tracked")
                % {"doctype": dt.name, "field": field},
                "DUPLICATE_DATA",
            )

        was_disabled = True
        if self.id:
            was_disabled = bool(
                await grunt.db.get_value("MilestoneTracker", self.id, "disabled")
            ) or not await grunt.db.exists("MilestoneTracker", self.id)
        self._starts = was_disabled and not self.get("disabled")

    async def after_save(self) -> None:
        milestones.invalidate()
        if self._starts:
            # Existing documents get their current value as an (approximate) start.
            async with grunt.system_context(grunt.get_session()):
                await milestones.seed(self.ref_doctype, self.track_field)
