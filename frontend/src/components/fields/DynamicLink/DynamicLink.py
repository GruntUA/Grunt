from grunt.metadata.field import FieldType, register_field_type_class


class DynamicLinkField(FieldType):
    name = "DynamicLink"
    sa_factory = staticmethod(lambda f: ("String", 255))
    python_type = "str | None"


def register():
    register_field_type_class(DynamicLinkField)
