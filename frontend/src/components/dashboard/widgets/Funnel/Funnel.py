"""funnel widget — backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_funnel


class Funnel(WidgetType):
    name = "funnel"

    compute = staticmethod(_widget_funnel)


def register() -> None:
    register_widget_type_class(Funnel)
