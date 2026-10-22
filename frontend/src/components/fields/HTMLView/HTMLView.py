from grunt.metadata.field import FieldType, register_field_type_class
lazy from grunt.utils.sanitize import sanitize_html


class HTMLViewField(FieldType):
    """Markup the server builds (a summary table, a report) - shown rendered, never edited.

    Sanitized on every write like RichText, so the form can render it as is.
    """

    name = "HTMLView"
    column_spec = ("Text",)
    searchable = False
    python_type = "str | None"
    traits = frozenset({"html"})

    @classmethod
    def parse(cls, value):
        if not isinstance(value, str):
            return value

        return sanitize_html(value)


def register():
    register_field_type_class(HTMLViewField)
