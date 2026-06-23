from grunt.metadata.field import FieldType, register_field_type_class


class EmbeddedFormField(FieldType):
    name = "EmbeddedForm"
    sa_factory = staticmethod(lambda f: ("JSON",))
    searchable = False
    python_type = "dict | None"


def register():
    register_field_type_class(EmbeddedFormField)
