from typing import Any

from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import build_response
from grunt.i18n import N_
from grunt.monitoring.health import skeleton


class SystemHealthReport(BaseDocument):
    """«Стан системи» - computed live on every open, nothing is stored (read-only).

    Opens at once on a skeleton: every section pending. The page's client
    script (SystemHealthReport.js) then runs the sections in parallel
    (health.run_section) and the browser's own checks, filling each in as it
    arrives.
    """

    not_supported_message = N_("The system health report is read-only")

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        self.data = {"name": self.doctype, **skeleton()}

    @classmethod
    async def get_list(cls, doctype: str, **kwargs: Any) -> DocumentList:
        # The single row, without running the checks - lists and counts only need the name.
        return build_response([{"name": doctype}], 1, 1)
