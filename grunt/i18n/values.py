"""Field values as text for the reader - the server's ``formatValue``.

What the desk shows through ``frontend/src/core/formatValue.ts`` and the field
types' ``format.ts``, for pages the server renders (list export, print): dates
in SystemSettings ``date_format`` / ``timezone``, numbers with the UI language's
separators and the field's ``precision``, money with its currency, durations,
byte sizes, ratings.

The result is plain text - escape it before putting it into HTML.
"""

import math
from datetime import UTC, date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from grunt.i18n.service import _, translation_service
from grunt.metadata.field import is_numeric_fieldtype
lazy from grunt.site.settings import get_system_settings

#: Shown for an empty value.
EMPTY_VALUE = "—"

_DURATION_UNITS = (
    ("{n} d", 86_400_000),
    ("{n} h", 3_600_000),
    ("{n} min", 60_000),
    ("{n} s", 1_000),
)
_BYTE_UNITS = ("KB", "MB", "GB", "TB")

# Symbols the desk shows (Intl ``narrowSymbol``) for the usual currencies;
# any other code is printed as is.
_CURRENCY_SYMBOLS = {"UAH": "₴", "USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł"}


class FormatField(Protocol):
    fieldtype: str
    options: str | None


class ValueFormatter:
    """Plain-text values for one page - settings are read once, not per value."""

    def __init__(self, date_format: str, tz: ZoneInfo | None, lang: str) -> None:
        self.date_format = date_format
        self.tz = tz
        # uk (and the rest of continental Europe): `1 234,5`; en: `1,234.5`.
        self.comma_decimal = lang != "en"

    def number(self, n: float, precision: int | None = None) -> str:
        """*n* with the language's separators: *precision* decimals, else up to 3."""
        if precision is None:
            s = f"{n:,.3f}".rstrip("0").rstrip(".")
        else:
            s = f"{n:,.{max(precision, 0)}f}"
        if self.comma_decimal:
            s = s.replace(",", "\u00a0").replace(".", ",")
        return s

    def date(self, value: Any, *, time: bool = False) -> str:
        d = to_datetime(value)
        if d is None:
            return str(value)
        if time and isinstance(d, datetime):
            # Server timestamps are UTC; a naive one is tagged before converting.
            if d.tzinfo is None:
                d = d.replace(tzinfo=UTC)
            if self.tz:
                d = d.astimezone(self.tz)
        y, m, day = f"{d.year:04d}", f"{d.month:02d}", f"{d.day:02d}"
        out = {
            "yyyy-mm-dd": f"{y}-{m}-{day}",
            "dd/mm/yyyy": f"{day}/{m}/{y}",
        }.get(self.date_format, f"{day}.{m}.{y}")
        if time and isinstance(d, datetime):
            out += f" {d.hour:02d}:{d.minute:02d}"
        return out

    def time(self, value: Any) -> str:
        if isinstance(value, time):
            return f"{value.hour:02d}:{value.minute:02d}"
        try:
            t = time.fromisoformat(str(value))
        except ValueError:
            return str(value)
        return f"{t.hour:02d}:{t.minute:02d}"

    def duration(self, value: Any, field: FormatField) -> str:
        n = to_float(value)
        if n is None:
            return str(value)
        ms_unit = (field.options or "").strip().lower() == "ms"
        sign = "−" if n < 0 else ""
        rest = round(abs(n) * (1 if ms_unit else 1000))
        if ms_unit and rest < 1000:
            return sign + _("{n} ms").replace("{n}", str(rest))
        rest = round(rest / 1000) * 1000
        parts = []
        for key, size in _DURATION_UNITS:
            count, rest = divmod(rest, size)
            if count:
                parts.append(_(key).replace("{n}", str(count)))
        return sign + (" ".join(parts) or _("{n} s").replace("{n}", "0"))

    def bytes(self, n: float) -> str:
        if abs(n) < 1024:
            return f"{self.number(n)} {_('B')}"
        value, i = n / 1024, 0
        while abs(value) >= 1024 and i < len(_BYTE_UNITS) - 1:
            value /= 1024
            i += 1
        return f"{self.number(round(value, 1 if abs(value) < 10 else 0))} {_(_BYTE_UNITS[i])}"

    def currency(self, n: float, code: str | None, precision: int | None) -> str:
        """`12 345,67 ₴` - or without the sign when the currency is unknown."""
        text = self.number(n, 2 if precision is None else precision)
        if not code:
            return text
        return f"{text} {_CURRENCY_SYMBOLS.get(code, code)}"

    @staticmethod
    def rating(n: float) -> str:
        """`★★★½☆ 3.5` - out of 5; anything outside 0-5 stays a number."""
        if n < 0 or n > 5:
            return f"{n:g}"
        full = math.floor(n)
        half = n - full >= 0.5
        return "★" * full + ("½" if half else "") + "☆" * (5 - full - half) + f" {n:g}"

    def __call__(self, value: Any, field: FormatField, doc: dict[str, Any] | None = None) -> str:
        """*value* of *field* as text, ``—`` when empty. *doc* (the row the value
        is from) names a Currency field's currency through a sibling field."""
        if value is None or value == "":
            return EMPTY_VALUE
        precision = getattr(field, "precision", None)
        match field.fieldtype:
            case "Date":
                return self.date(value)
            case "Datetime":
                return self.date(value, time=True)
            case "Time":
                return self.time(value)
            case "Duration":
                return self.duration(value, field)
            case "Check":
                return "✓" if value in (True, 1, "1", "true") else "✗"
            case "Geolocation" if isinstance(value, dict) and "lat" in value and "lng" in value:
                return f"{float(value['lat']):.5f}, {float(value['lng']):.5f}"
        if is_numeric_fieldtype(field.fieldtype) and (n := to_float(value)) is not None:
            match field.fieldtype:
                case "Int" if field.options == "Bytes":
                    return self.bytes(n)
                case "Currency":
                    return self.currency(n, currency_code(field, doc), precision)
                case "Percent":
                    return f"{self.number(n, precision)} %"
                case "Rating":
                    return self.rating(n)
            return self.number(n, precision)
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v not in (None, ""))
        return str(value)


def currency_code(field: FormatField, doc: dict[str, Any] | None) -> str | None:
    """A Currency field's ``options``: a sibling field holding the code, or the code itself."""
    opt = (field.options or "").strip()
    if not opt:
        return None
    if doc is not None and opt in doc:
        code = doc.get(opt)
        return code if isinstance(code, str) and code else None
    return opt if len(opt) == 3 and opt.isalpha() and opt.isupper() else None


async def site_value_formatter() -> ValueFormatter:
    """A formatter for the site's date format / time zone and the current language."""
    settings = await get_system_settings()
    tz_name = settings.get("timezone")
    try:
        tz = ZoneInfo(tz_name) if tz_name else None
    except Exception:  # noqa: BLE001 - an unknown zone name: times stay in UTC
        tz = None
    return ValueFormatter(
        settings.get("date_format") or "dd.mm.yyyy", tz, translation_service.get_lang()
    )


def to_datetime(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        s = str(value).strip()
        return datetime.fromisoformat(s) if len(s) > 10 else date.fromisoformat(s)
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except TypeError, ValueError:
        return None
    return n if math.isfinite(n) else None
