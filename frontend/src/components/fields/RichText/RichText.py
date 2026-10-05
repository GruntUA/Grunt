from grunt.metadata.field import FieldType, register_field_type_class


class RichTextField(FieldType):
    """HTML from the tiptap editor - sanitized on every write (grunt.utils.sanitize)."""

    name = "RichText"
    column_spec = staticmethod(lambda f: ("Text",))
    python_type = "str | None"

    @classmethod
    def coerce(cls, value):
        if not isinstance(value, str) or not value:
            return value
        from grunt.utils.sanitize import sanitize_html

        return sanitize_html(value)


def register():
    register_field_type_class(RichTextField)
