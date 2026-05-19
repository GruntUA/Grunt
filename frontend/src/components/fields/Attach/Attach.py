from grunt.metadata.field import FieldType, register_field_type_class


class AttachField(FieldType):
    name = "Attach"
    sa_factory = staticmethod(lambda f: ("String", 500))
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(AttachField)
