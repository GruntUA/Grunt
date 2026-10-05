"""Utility API mixin for GruntApp facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grunt.local import require_user
from grunt.metadata.registry import doctype_registry
from grunt.site.manager import site_manager
from grunt.tasks.doc_method import enqueue_doc_method
from grunt.utils.templates import render_template as _render_template

if TYPE_CHECKING:
    from grunt.document.meta import Meta


class UtilityAPI:
    """Utility helpers exposed on the top-level GruntApp facade."""

    async def enqueue_doc(
        self,
        doctype: str,
        doc_id: str,
        method: str,
        **kwargs: Any,
    ) -> None:
        """Enqueue a controller method to run as a background task.

        The method must exist on the DocType controller and is called with
        ``**kwargs`` in a fresh site context::

            await grunt.enqueue_doc("Report", report_id, "generate", format="pdf")
        """
        user = require_user()
        await enqueue_doc_method(
            site=site_manager.get_active_site(),
            user_email=user.email,
            doctype=doctype,
            doc_id=doc_id,
            method=method,
            kwargs=kwargs,
        )

    async def get_meta(self, doctype: str) -> Meta | None:
        """Return the :class:`~grunt.document.meta.Meta` wrapper, or ``None``
        if ``doctype`` isn't a registered DocType.
        """
        return await doctype_registry.get_meta(doctype)

    async def render_template(
        self,
        template: str,
        context: dict[str, Any] | None = None,
        *,
        autoescape: bool = True,
    ) -> str:
        """Render a Jinja2 template and return the result as a string."""
        return await _render_template(self, template, context, autoescape=autoescape)
