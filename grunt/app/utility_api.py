"""Utility API mixin for GruntApp facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from grunt.errors import GruntError
from grunt.utils.templates import render_template as _render_template

if TYPE_CHECKING:
    from grunt.document.meta import Meta

logger = structlog.get_logger()


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
        from grunt.site.manager import site_manager
        from grunt.tasks.doc_method import enqueue_doc_method

        user = self._require_user()
        await enqueue_doc_method(
            site=site_manager.get_active_site(),
            user_email=user.email,
            doctype=doctype,
            doc_id=doc_id,
            method=method,
            kwargs=kwargs,
        )

    async def get_meta(self, doctype: str) -> Meta:
        """Return the :class:`~grunt.core.document.meta.Meta` wrapper."""
        from grunt.document.meta import Meta
        from grunt.metadata.registry import doctype_registry

        dt = await doctype_registry.get(doctype)
        return Meta(dt)

    def throw(self, message: str, title: str | None = None) -> None:
        """Raise a user-facing :class:`GruntError`."""
        raise GruntError(message, title=title)

    def log(self, *args: Any) -> None:
        """Log a message via structlog (also captured in server script output)."""
        logger.info("grunt.log", message=" ".join(str(a) for a in args))

    def _(self, source: str) -> str:
        """Translate a string using the current request language."""
        from grunt.i18n import _ as _translate

        return _translate(source)

    async def render_template(
        self,
        template: str,
        context: dict[str, Any] | None = None,
        *,
        autoescape: bool = True,
    ) -> str:
        """Render a Jinja2 template and return the result as a string."""
        return await _render_template(self, template, context, autoescape=autoescape)
