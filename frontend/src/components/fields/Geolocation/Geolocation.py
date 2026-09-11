from grunt.metadata.field import FieldType, register_field_type_class


class GeolocationField(FieldType):
    name = "Geolocation"
    column_spec = staticmethod(lambda f: ("JSON",))
    searchable = False
    python_type = "str | None"


def register():
    register_field_type_class(GeolocationField)
