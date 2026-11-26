"""List-report options beyond plain columns: fixed conditions and date grouping.

* ``conditions`` - ``[{"fieldname", "op", "value"}]`` always applied to the
  report (unlike ``filters_config``, which only offers filters to the viewer).
  Operators use the filter-bar vocabulary; a date value may be relative:
  ``today``, ``today-30``, ``today+7`` (days) - kept as given, the query
  resolves it by the column (:mod:`grunt.utils.dates`).
* ``date_group`` on a grouping column - ``day`` / ``month`` / ``quarter`` /
  ``year``: rows are grouped by that period, labelled ``2026-09-23``,
  ``2026-09``, ``2026-Q3``, ``2026``.
"""

from typing import Any

from grunt.query.parse import DISPLAY_OPS


def compile_conditions(conditions: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Each condition as a one-key filter dict (``grunt.query.parse``) (keys may repeat across
    conditions - e.g. a date range - so they are not merged into one dict)."""
    out: list[dict[str, Any]] = []
    for c in conditions or []:
        field, op = c.get("fieldname"), c.get("op") or "="
        if not field or op not in DISPLAY_OPS:
            continue
        if op in ("is set", "is not set"):
            out.append({f"{field}__is": "not set" if op == "is not set" else "set"})
            continue
        value = c.get("value")
        if op in ("in", "not in"):
            items = value if isinstance(value, list) else str(value or "").split(",")
            value = [str(v).strip() for v in items if str(v).strip()]
        if value in (None, "", []):
            continue
        out.append({f"{field}__{DISPLAY_OPS[op]}": value})
    return out
