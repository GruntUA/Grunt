from grunt.metadata.field import FieldType, register_field_type_class


class SelectField(FieldType):
    name = "Select"
    column_spec = staticmethod(lambda f: ("String", 100))
    python_type = "str | None"


def register():
    register_field_type_class(SelectField)
