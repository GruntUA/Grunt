"""FormTour controller - every step points at a field the DocType has."""

from __future__ import annotations

from grunt import _
from grunt.document.base import Document


class FormTour(Document):
    async def validate(self) -> None:
        meta = await self.grunt.get_meta(self.get("reference_doctype") or "")
        if meta is None:
            self.grunt.throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.get("reference_doctype")}
            )
        for step in self.get("steps") or []:
            fieldname = step.get("fieldname")
            if fieldname and not meta.has_field(fieldname):
                self.grunt.throw(
                    _("Step “%(step)s”: field “%(field)s” not found")
                    % {"step": step.get("title"), "field": fieldname}
                )
