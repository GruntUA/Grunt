"""donut widget — backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_donut


class Donut(WidgetType):
    name = "donut"

    compute = staticmethod(_widget_donut)


def register() -> None:
    register_widget_type_class(Donut)
