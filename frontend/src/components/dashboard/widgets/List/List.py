"""list widget - backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_list


class ListWidget(WidgetType):
    name = "list"

    compute = staticmethod(_widget_list)


def register() -> None:
    register_widget_type_class(ListWidget)
