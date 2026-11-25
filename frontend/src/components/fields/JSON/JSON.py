from grunt.metadata.field import FieldType, register_field_type_class


class JSONField(FieldType):
    name = "JSON"
    column_spec = ("JSON",)
    searchable = False
    python_type = "Any | None"


def register():
    register_field_type_class(JSONField)
