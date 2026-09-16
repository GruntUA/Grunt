"""links widget — renders entirely client-side from `content`; no backend computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class


class Links(WidgetType):
    name = "links"
    requires_backend_compute = False


def register() -> None:
    register_widget_type_class(Links)
