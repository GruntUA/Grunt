from grunt.metadata.field import FieldType, register_field_type_class


class ColumnField(FieldType):
    name = "Column"
    sa_factory = None  # non-physical: UI layout element only
    searchable = False
    python_type = "None"


def register():
    register_field_type_class(ColumnField)
