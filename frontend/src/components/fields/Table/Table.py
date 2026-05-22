from grunt.metadata.field import FieldType, register_field_type_class


class TableField(FieldType):
    name = "Table"
    sa_factory = None  # non-physical: stored in a child table, not a column
    searchable = False
    python_type = "list[dict] | None"


def register():
    register_field_type_class(TableField)
