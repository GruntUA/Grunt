from grunt.metadata.field import FieldType, register_field_type_class


class ColumnMappingField(FieldType):
    name = "ColumnMapping"
    column_spec = staticmethod(lambda f: ("JSON",))
    searchable = False
    python_type = "dict[str, str] | None"


def register():
    register_field_type_class(ColumnMappingField)
