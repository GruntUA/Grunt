from grunt.metadata.field import FieldType, register_field_type_class


class ColorField(FieldType):
    name = "Color"
    column_spec = staticmethod(lambda f: ("String", 20))
    python_type = "str | None"


def register():
    register_field_type_class(ColorField)
