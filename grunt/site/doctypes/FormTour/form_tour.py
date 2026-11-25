"""FormTour controller - every step points at a field the DocType has (a
list tour may also point at a standard column: name, modified_at, ...)."""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.metadata.compiler import STANDARD_COLUMNS
from grunt.site.doctypes.FormTourStep.form_tour_step import FormTourStep


class FormTour(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    reference_doctype: str  # Document type
    view: str | None = None  # Shown in
    app: str | None = None  # App
    is_published: bool | None = None  # Published
    auto_start: bool | None = None  # Start automatically
    roles: str | None = None  # Roles (comma-separated)
    is_standard: bool | None = None  # Standard
    steps: list[FormTourStep] = []  # Steps

    # end: auto-generated types

    async def validate(self) -> None:
        meta = await self.grunt.get_meta(self.reference_doctype or "")
        if meta is None:
            throw(_("DocType “%(doctype)s” not found") % {"doctype": self.reference_doctype})
        columns = STANDARD_COLUMNS if self.view == "List" else ()
        for step in self.steps or []:
            fieldname = step.fieldname
            if fieldname and not meta.has_field(fieldname) and fieldname not in columns:
                throw(
                    _("Step “%(step)s”: field “%(field)s” not found")
                    % {"step": step.title, "field": fieldname}
                )
