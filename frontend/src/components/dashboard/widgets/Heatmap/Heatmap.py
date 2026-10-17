"""heatmap widget - backend data computation."""

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_heatmap


class Heatmap(WidgetType):
    name = "heatmap"

    compute = staticmethod(_widget_heatmap)


def register() -> None:
    register_widget_type_class(Heatmap)
