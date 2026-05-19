from grunt.metadata.field import FieldType, register_field_type_class


class CodeField(FieldType):
    name = "Code"
    sa_factory = staticmethod(lambda f: ("Text",))
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(CodeField)
