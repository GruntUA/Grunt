"""text widget - renders entirely client-side from `content`; no backend computation."""

from grunt.metadata.widget import WidgetType, register_widget_type_class


class Text(WidgetType):
    name = "text"
    requires_backend_compute = False


def register() -> None:
    register_widget_type_class(Text)
