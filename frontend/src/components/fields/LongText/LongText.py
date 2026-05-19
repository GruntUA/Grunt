from grunt.metadata.field import FieldType, register_field_type_class


class LongTextField(FieldType):
    name = "LongText"
    sa_factory = staticmethod(lambda f: ("Text",))
    python_type = "str | None"


def register():
    register_field_type_class(LongTextField)
