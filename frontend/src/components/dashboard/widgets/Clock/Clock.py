"""clock widget — renders entirely client-side; no backend computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class


class Clock(WidgetType):
    name = "clock"
    requires_backend_compute = False


def register() -> None:
    register_widget_type_class(Clock)
