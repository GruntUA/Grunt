"""gauge widget - backend data computation.

Shares metric's compute (same aggregation/trend shape).
"""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_metric


class Gauge(WidgetType):
    name = "gauge"

    compute = staticmethod(_widget_metric)


def register() -> None:
    register_widget_type_class(Gauge)
