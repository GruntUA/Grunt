from grunt.metadata.field import FieldType, register_field_type_class


class LinkField(FieldType):
    name = "Link"
    sa_factory = staticmethod(lambda f: ("String", 255))
    python_type = "str | None"


def register():
    register_field_type_class(LinkField)
