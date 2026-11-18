from grunt.metadata.field import FieldType, register_field_type_class
from grunt.utils.numbers import round_to_precision

# Kopecks, unless the field says otherwise.
DEFAULT_PRECISION = 2


def currency_precision(field) -> int:
    precision = getattr(field, "precision", None)
    return DEFAULT_PRECISION if precision is None else int(precision)


def currency_column(field) -> tuple:
    """``NUMERIC(18, precision)`` - the field's decimals, 2 by default."""
    return ("Numeric", 18, currency_precision(field))


class CurrencyField(FieldType):
    """Money amount - exact NUMERIC column, rounded to the field's ``precision``
    (default 2) on write by the site's rounding method (grunt.utils.numbers).

    ``options`` names the currency: a fieldname of a Link to Currency on the same
    doc, or a fixed ISO code (e.g. ``UAH``). Display only; storage ignores it.
    """

    name = "Currency"
    empty_as_null = True
    python_type = "float | None"

    # A precision change is a column change (scale) - see grunt.db.schema.diff.
    column_spec = staticmethod(currency_column)

    @classmethod
    def parse(cls, value):
        try:
            return float(value)
        except TypeError, ValueError:
            return None

    @classmethod
    def coerce_field(cls, field, value):
        return round_to_precision(cls.coerce(value), currency_precision(field))


def register():
    register_field_type_class(CurrencyField)
