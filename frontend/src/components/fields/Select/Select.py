from grunt.metadata.field import FieldType, register_field_type_class


class SelectField(FieldType):
    name = "Select"
    sa_factory = staticmethod(lambda f: ("String", 100))
    python_type = "str | None"


def register():
    register_field_type_class(SelectField)
