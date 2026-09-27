"""WebPage DocType controller."""

from __future__ import annotations

from typing import Any

from grunt.document.base import Document


class WebPage(Document):
    """A CMS page, served at its own absolute ``route`` (grunt.website.router)."""

    @staticmethod
    def get_web_url(doc: dict[str, Any]) -> str | None:
        route = doc.get("route")
        return route if doc.get("published") and route else None
