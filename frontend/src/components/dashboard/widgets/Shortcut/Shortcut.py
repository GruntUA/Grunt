"""shortcut widget - backend data computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class
from grunt.reports.widget_compute import _widget_shortcut


class Shortcut(WidgetType):
    name = "shortcut"

    compute = staticmethod(_widget_shortcut)


def register() -> None:
    register_widget_type_class(Shortcut)
