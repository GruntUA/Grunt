"""Rounding of numbers to a field's precision (FRAPPE_GAP_PLAN #5).

Through :class:`~decimal.Decimal` from the number's shortest text form, so the
binary float doesn't leak in: ``round(1.005, 2)`` is ``1.0`` in Python (1.005
is 1.00499... in binary), here it's ``1.01``. The same rules as
``frontend/src/core/numbers.ts``.

The method is the site's ``SystemSettings.rounding_method``:

* ``Half up`` (commercial, the default) - a 5 goes away from zero: 0.125 -> 0.13;
* ``Half even`` (banker's) - a 5 goes to the even digit: 0.125 -> 0.12, 0.135 -> 0.14.
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

from grunt.site.manager import current_site

HALF_UP = "Half up"
HALF_EVEN = "Half even"
DEFAULT_ROUNDING = HALF_UP

_MODES = {HALF_UP: ROUND_HALF_UP, HALF_EVEN: ROUND_HALF_EVEN}

# site -> its rounding method, kept up to date by grunt.site.settings whenever it
# reads the settings row (the write paths read it first). Value coercion is sync
# and sits below the settings, so it reads this instead of querying.
_site_rounding: dict[str, str] = {}


def set_site_rounding(site: str, method: str | None) -> None:
    """Remember *site*'s ``rounding_method`` (called by grunt.site.settings)."""
    _site_rounding[site] = method or DEFAULT_ROUNDING


def site_rounding() -> str:
    """The current site's rounding method (half up until its settings were read)."""
    return _site_rounding.get(current_site.get(), DEFAULT_ROUNDING)


def round_to_precision(value: float | None, precision: int | None) -> float | None:
    """*value* rounded to a field's *precision* by the site's method; as is
    when either is ``None``."""
    if value is None or precision is None:
        return value
    return round_number(value, precision, site_rounding())


def round_number(value: float, precision: int, method: str | None = None) -> float:
    """*value* rounded to *precision* decimal places by *method* (default half up)."""
    try:
        exact = Decimal(repr(float(value)))
        rounded = exact.quantize(
            Decimal(1).scaleb(-int(precision)),
            rounding=_MODES.get(method or DEFAULT_ROUNDING, ROUND_HALF_UP),
        )
    except InvalidOperation, ValueError, OverflowError:
        return value
    return float(rounded)
