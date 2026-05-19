from grunt.metadata.field import FieldType, register_field_type_class


class MultiLinkField(FieldType):
    name = "MultiLink"
    sa_factory = None  # non-physical
    searchable = False
    python_type = "list[str] | None"


def register():
    register_field_type_class(MultiLinkField)
