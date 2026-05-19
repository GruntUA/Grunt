from grunt.metadata.field import FieldType, register_field_type_class


class HTMLEditorField(FieldType):
    name = "HTMLEditor"
    sa_factory = staticmethod(lambda f: ("Text",))
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(HTMLEditorField)
