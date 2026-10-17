from grunt.metadata.field import FieldType, register_field_type_class, varchar_spec


class DataField(FieldType):
    name = "Data"
    column_spec = staticmethod(varchar_spec)
    python_type = "str | None"


def register():
    register_field_type_class(DataField)
