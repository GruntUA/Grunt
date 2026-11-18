from grunt.metadata.field import FieldType, parse_float, register_field_type_class
from grunt.utils.numbers import round_to_precision


class FloatField(FieldType):
    name = "Float"
    column_spec = ("Double",)
    empty_as_null = True
    python_type = "float | None"

    @classmethod
    def parse(cls, value):
        return parse_float(value)

    @classmethod
    def coerce_field(cls, field, value):
        # Rounded only when the field sets a precision.
        return round_to_precision(cls.coerce(value), getattr(field, "precision", None))


def register():
    register_field_type_class(FloatField)
