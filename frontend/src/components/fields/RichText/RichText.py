from grunt.metadata.field import FieldType, register_field_type_class


class RichTextField(FieldType):
    name = "RichText"
    column_spec = staticmethod(lambda f: ("Text",))
    python_type = "str | None"


def register():
    register_field_type_class(RichTextField)
