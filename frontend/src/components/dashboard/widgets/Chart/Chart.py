"""chart_area / chart_bar widgets - backend data computation. Both render the
same time-series shape; only the frontend rendering (line vs bar) differs.
"""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_chart


class ChartArea(WidgetType):
    name = "chart_area"

    compute = staticmethod(_widget_chart)


class ChartBar(WidgetType):
    name = "chart_bar"

    compute = staticmethod(_widget_chart)


def register() -> None:
    register_widget_type_class(ChartArea)
    register_widget_type_class(ChartBar)
