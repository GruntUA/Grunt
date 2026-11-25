"""ModuleOnboarding controller - every step gets a stable ``step_id``.

Child rows are re-created when a standard record is applied from its files,
so their ``name`` can't key the progress. ``step_id`` is set once from the
title and kept (and exported with the record) when the title changes later.
"""

from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.utils.slug import slugify


class ModuleOnboarding(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Title
    subtitle: str | None = None  # Subtitle
    app: str | None = None  # App
    is_published: bool | None = None  # Published
    roles: str | None = None  # Roles (comma-separated)
    progress_scope: str | None = None  # Progress
    success_message: str | None = None  # Success message
    documentation_url: str | None = None  # Documentation URL
    is_standard: bool | None = None  # Standard
    steps: list[dict] = []  # Table: OnboardingStep

    # end: auto-generated types

    async def validate(self) -> None:
        taken: set[str] = set()
        for step in self.steps or []:
            step_id = step.get("step_id") or slugify(step.get("title") or "")
            base, n = step_id, 2
            while step_id in taken:
                step_id, n = f"{base}-{n}", n + 1
            step["step_id"] = step_id
            taken.add(step_id)

            doctype = step.get("reference_doctype")
            if doctype and await self.grunt.get_meta(doctype) is None:
                throw(
                    _("Step “%(step)s”: DocType “%(doctype)s” not found")
                    % {"step": step.get("title"), "doctype": doctype}
                )
