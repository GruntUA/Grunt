from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from grunt.i18n import _
from grunt.metadata.virtual import VirtualDocType
from grunt.monitoring.health import build_report


class SystemHealthReportController(VirtualDocType):
    """«Стан системи» — computed live on every open, nothing is stored.

    The browser tab (``browser_checks``) is filled in by the page's client
    script (SystemHealthReport.js): those checks can only run in the browser.
    """

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"name": self.doctype, "browser_checks": [], **await build_report()}

    async def get_list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # The single row, without running the checks — lists and counts only need the name.
        return self.build_response([{"name": self.doctype}], 1, 1)

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED, _("The system health report is read-only")
        )

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED, _("The system health report is read-only")
        )

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED, _("The system health report is read-only")
        )
