"""FormTour controller - every step points at a field the DocType has (a
list tour may also point at a standard column: name, modified_at, ...)."""

from grunt.document.base import Document
from grunt.i18n import _
from grunt.metadata.compiler import STANDARD_COLUMNS


class FormTour(Document):
    async def validate(self) -> None:
        meta = await self.grunt.get_meta(self.get("reference_doctype") or "")
        if meta is None:
            self.grunt.throw(
                _("DocType “%(doctype)s” not found") % {"doctype": self.get("reference_doctype")}
            )
        columns = STANDARD_COLUMNS if self.get("view") == "List" else ()
        for step in self.get("steps") or []:
            fieldname = step.get("fieldname")
            if fieldname and not meta.has_field(fieldname) and fieldname not in columns:
                self.grunt.throw(
                    _("Step “%(step)s”: field “%(field)s” not found")
                    % {"step": step.get("title"), "field": fieldname}
                )
