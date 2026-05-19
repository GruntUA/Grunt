from grunt.metadata.field import FieldType, register_field_type_class

_MIN_VARCHAR = 64
_MAX_VARCHAR = 1000


class DataField(FieldType):
    name = "Data"
    sa_factory = staticmethod(
        lambda f: ("String", max(_MIN_VARCHAR, min(f.max_length or 255, _MAX_VARCHAR)))
    )
    python_type = "str | None"


def register():
    register_field_type_class(DataField)
