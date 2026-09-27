"""WebForm DocType controller."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from grunt.document.base import Document


class WebForm(Document):
    """A public form, served at ``/form/<route>`` (grunt/website/www/form/)."""

    @staticmethod
    def get_web_url(doc: dict[str, Any]) -> str | None:
        route = doc.get("route")
        return f"/form/{quote(route)}" if doc.get("is_published") and route else None
