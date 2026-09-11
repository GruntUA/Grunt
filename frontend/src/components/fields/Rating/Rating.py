from grunt.metadata.field import FieldType, register_field_type_class


class RatingField(FieldType):
    name = "Rating"
    column_spec = staticmethod(lambda f: ("Float", 2))
    empty_as_null = True
    python_type = "int | None"

    @classmethod
    def coerce(cls, value):
        if value is None or value == "":
            return None
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return value


def register():
    register_field_type_class(RatingField)
