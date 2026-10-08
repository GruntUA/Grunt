"""PageWidget.widget_type offers every registered widget type - an app's own too."""

from grunt.metadata import widget
from grunt.metadata.dynamic_options import get_options


def test_registered_widget_types_are_offered():
    class AppWidget(widget.WidgetType):
        name = "app_test_widget"
        requires_backend_compute = False

    widget.register_widget_type_class(AppWidget)
    try:
        options = get_options(widget.WIDGET_TYPE_SOURCE)
        assert {"metric", "table", "app_test_widget"} <= set(options)
    finally:
        widget._WIDGET_TYPE_REGISTRY.pop("app_test_widget", None)
