"""table widget - backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_table


class TableWidget(WidgetType):
    name = "table"

    compute = staticmethod(_widget_table)


def register() -> None:
    register_widget_type_class(TableWidget)
