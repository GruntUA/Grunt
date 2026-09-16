"""shortcuts_grid widget — renders entirely client-side from `content`; no backend computation."""

from __future__ import annotations

from grunt.metadata.widget import WidgetType, register_widget_type_class


class ShortcutsGrid(WidgetType):
    name = "shortcuts_grid"
    requires_backend_compute = False


def register() -> None:
    register_widget_type_class(ShortcutsGrid)
