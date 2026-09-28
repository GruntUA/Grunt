from grunt.metadata.field import FieldType, register_field_type_class


class CurrencyField(FieldType):
    """Money amount — exact NUMERIC column, rounded to kopecks on write.

    ``options`` names the currency: a fieldname of a Link to Currency on the same
    doc, or a fixed ISO code (e.g. ``UAH``). Display only; storage ignores it.
    """

    name = "Currency"
    column_spec = staticmethod(lambda f: ("Numeric", 18, 2))
    empty_as_null = True
    python_type = "float | None"

    @classmethod
    def coerce(cls, value):
        if value is None or value == "":
            return None
        try:
            return round(float(value), 2)
        except TypeError, ValueError:
            return None


def register():
    register_field_type_class(CurrencyField)
