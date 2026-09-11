from grunt.metadata.field import FieldType, register_field_type_class


class LongTextField(FieldType):
    name = "LongText"
    column_spec = staticmethod(lambda f: ("Text",))
    python_type = "str | None"


def register():
    register_field_type_class(LongTextField)
