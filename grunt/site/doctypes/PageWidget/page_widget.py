"""Controller for the ``PageWidget`` DocType."""

from typing import Any

from grunt.document.base import Document


class PageWidget(Document):
    """DocType controller for PageWidget."""

    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    widget_type: str | None = None  # Type
    title: str | None = None  # Title
    ref_doctype: str | None = None  # DocType
    aggregation: str | None = None  # Aggregation
    field: str | None = None  # Field
    value_label: str | None = None  # Value label
    row_limit: int | None = None  # Rows
    group_by: str | None = None  # Group by
    date_field: str | None = None  # Date field
    period: str | None = None  # Period
    period_switch: bool | None = None  # Period switcher
    filters: Any | None = None  # Filters
    min_value: int | None = None  # Min. value
    max_value: int | None = None  # Max. value
    cols: int | None = None  # Width (1-4)
    color: str | None = None  # Color
    icon: str | None = None  # Icon (lucide)
    link_type: str | None = None  # Link type
    description: str | None = None  # Description / Subtitle
    report: str | None = None  # Report (chart data source)
    content: str | None = None  # Content

    # end: auto-generated types
