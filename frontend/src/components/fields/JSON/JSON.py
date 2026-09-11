from grunt.metadata.field import FieldType, register_field_type_class


class JSONField(FieldType):
    name = "JSON"
    column_spec = staticmethod(lambda f: ("JSON",))
    searchable = False
    python_type = "dict | None"


def register():
    register_field_type_class(JSONField)
