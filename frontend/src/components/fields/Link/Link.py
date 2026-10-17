from grunt.metadata.field import FieldType, register_field_type_class


class LinkField(FieldType):
    name = "Link"
    traits = frozenset({"link"})
    column_spec = ("String", 255)
    python_type = "str | None"


def register():
    register_field_type_class(LinkField)
