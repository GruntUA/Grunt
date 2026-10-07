from __future__ import annotations

from typing import Any

from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import build_response
from grunt.i18n import N_
from grunt.monitoring.health import build_report


class SystemHealthReportController(BaseDocument):
    """«Стан системи» - computed live on every open, nothing is stored (read-only).

    The browser tab (``browser_checks``) is filled in by the page's client
    script (SystemHealthReport.js): those checks can only run in the browser.
    """

    not_supported_message = N_("The system health report is read-only")

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        self.data = {"name": self.doctype, "browser_checks": [], **await build_report()}

    @classmethod
    async def get_list(cls, doctype: str, **kwargs: Any) -> DocumentList:
        # The single row, without running the checks - lists and counts only need the name.
        return build_response([{"name": doctype}], 1, 1)
