"""MilestoneTracker controller - validates the tracked field and seeds history.

The recording itself lives in :mod:`grunt.activity.milestones`.
"""

from grunt.activity import milestones
from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.registry import doctype_registry

_db = GruntDB()  # stateless: reads through the context's session


class MilestoneTracker(Document):
    """DocType controller for MilestoneTracker."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    ref_doctype: str  # Document type
    track_field: str | None = None  # Field
    disabled: bool | None = None  # Disabled

    # end: auto-generated types

    _starts: bool = False

    async def validate(self) -> None:
        meta = await doctype_registry.get_meta(self.ref_doctype)
        if meta is None:
            throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.ref_doctype},
                "VALIDATION_ERROR",
            )
        dt = meta.doc
        if dt.is_child or dt.is_singleton or not dt.has_table:
            throw(
                _("Milestones cannot be tracked on “%(doctype)s”") % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )

        field = (self.track_field or "").strip() or (dt.status_field or "")
        if not field:
            throw(
                _("%(doctype)s has no status field - choose the field to track")
                % {"doctype": dt.name},
                "VALIDATION_ERROR",
            )
        fdef = meta.get_field(field)
        if fdef is None or not fdef.is_physical or fdef.has_trait("table"):
            throw(
                _("“%(field)s” is not a field of %(doctype)s that can be tracked")
                % {"field": field, "doctype": dt.name},
                "VALIDATION_ERROR",
            )
        self.track_field = field

        duplicate = await _db.exists(
            "MilestoneTracker",
            {"ref_doctype": dt.name, "track_field": field, "name__ne": self.id or ""},
        )
        if duplicate:
            throw(
                _("%(doctype)s.%(field)s is already tracked")
                % {"doctype": dt.name, "field": field},
                "DUPLICATE_DATA",
            )

        was_disabled = True
        if self.id:
            was_disabled = bool(
                await _db.get_value("MilestoneTracker", self.id, "disabled")
            ) or not await _db.exists("MilestoneTracker", self.id)
        self._starts = was_disabled and not self.disabled

    async def after_save(self) -> None:
        milestones.invalidate()
        if self._starts and self.track_field:  # validate() always sets it
            # Existing documents get their current value as an (approximate) start.
            await milestones.seed(self.ref_doctype, self.track_field)
