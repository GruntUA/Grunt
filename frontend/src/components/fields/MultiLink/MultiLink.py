from grunt.metadata.field import FieldType, register_field_type_class


class MultiLinkField(FieldType):
    name = "MultiLink"
    column_spec = None  # non-physical
    searchable = False
    python_type = "list[str] | None"


def register():
    register_field_type_class(MultiLinkField)
