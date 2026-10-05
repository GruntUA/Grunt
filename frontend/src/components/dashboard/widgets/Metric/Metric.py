"""metric widget - backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_metric


class Metric(WidgetType):
    name = "metric"

    compute = staticmethod(_widget_metric)


def register() -> None:
    register_widget_type_class(Metric)
