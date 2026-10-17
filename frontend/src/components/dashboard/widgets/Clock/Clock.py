"""clock widget - renders entirely client-side; no backend computation."""

from grunt.metadata.widget import WidgetType, register_widget_type_class


class Clock(WidgetType):
    name = "clock"
    requires_backend_compute = False


def register() -> None:
    register_widget_type_class(Clock)
