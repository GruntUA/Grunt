from typing import Any

from grunt.document.base import Document
from grunt.i18n import N_
from grunt.monitoring.health import skeleton
from grunt.query.query import Query
from grunt.store import VirtualStore


class SystemHealthReportStore(VirtualStore):
    """«Стан системи» - computed live on every open, nothing is stored (read-only).

    Opens at once on a skeleton: every section pending. The page's client
    script (SystemHealthReport.js) then runs the sections in parallel
    (health.run_section) and the browser's own checks, filling each in as it
    arrives.
    """

    not_supported_message = N_("The system health report is read-only")

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        # The single row, without running the checks - lists and counts only need the name.
        return [{"name": self.doctype}]

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        return {"name": self.doctype, **skeleton()}


class SystemHealthReport(Document):
    store_class = SystemHealthReportStore
