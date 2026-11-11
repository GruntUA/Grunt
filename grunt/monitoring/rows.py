"""A row of the health report: ``{category, check, status, value, hint}``.

Shared by the checks in grunt/monitoring/health.py and grunt/monitoring/updates.py.
"""

from typing import Any

OK, WARNING, ERROR, INFO = "OK", "Warning", "Error", "Info"

Row = dict[str, Any]


def row(category: str, check: str, status: str, value: Any = "", hint: str = "") -> Row:
    return {
        "category": category,
        "check": check,
        "status": status,
        "value": "" if value is None else str(value),
        "hint": hint,
    }
