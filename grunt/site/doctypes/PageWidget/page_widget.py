"""Controller for the ``PageWidget`` DocType."""

from grunt.document.base import Document


class PageWidget(Document):
    """DocType controller for PageWidget."""

    widget_type: str | None
    title: str | None
    ref_doctype: str | None
    aggregation: str | None
    field: str | None
    value_label: str | None
    row_limit: int | None
    group_by: str | None
    date_field: str | None
    period: str | None
    period_switch: bool | None
    filters: dict | None
    min_value: int | None
    max_value: int | None
    cols: int | None
    color: str | None
    icon: str | None
    link_type: str | None
    description: str | None
    report: str | None
    content: str | None
