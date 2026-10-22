from grunt.metadata.field import FieldType, register_field_type_class
lazy from grunt.utils.sanitize import sanitize_html


class RichTextField(FieldType):
    """HTML from the tiptap editor - sanitized on every write (grunt.utils.sanitize)."""

    name = "RichText"
    column_spec = ("Text",)
    python_type = "str | None"
    traits = frozenset({"html"})

    @classmethod
    def parse(cls, value):
        if not isinstance(value, str):
            return value

        return sanitize_html(value)


def register():
    register_field_type_class(RichTextField)
