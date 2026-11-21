"""Naming pattern parser and formatter.

Supported patterns:
  - "field:title"           -> value of the 'title' field
  - "hash"                  -> short UUID (first 10 chars)
  - "prompt"                -> user must supply 'name' in data
  - "PREFIX-.YYYY.-.####"   -> pattern-based with counter
  - "INV-.MM.-.YYYY.-.#####" -> any combination of tokens
  - "ВХ-{department}-.YYYY.-.####" -> a field's value inside the name

Pattern tokens:
  .YYYY.  -> 4-digit year
  .YY.    -> 2-digit year
  .MM.    -> 2-digit month
  .DD.    -> 2-digit day
  .####.  -> zero-padded counter (width = number of #)
  {YYYY} {YY} {MM} {DD} {####} -> the same in braces (Frappe's "format:" style)
  {fieldname} -> the document's value of that field

Everything before the counter is the counter's key (``NamingSeries.prefix``),
so a field or a date before it starts a separate count per value.
"""

import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

# A token is a dotted .TOKEN. (the trailing dot is optional, so "INV-.####"
# works) or a braced {TOKEN}; in braces it may also be a field name.
_TOKEN_RE = re.compile(r"\.(#+|YYYY|YY|MM|DD)\.?|\{(#+|YYYY|YY|MM|DD|[A-Za-z_][A-Za-z0-9_]*)\}")

_DATE_TOKENS = frozenset({"YYYY", "YY", "MM", "DD"})

Part = str | tuple[str, int | str]


class MissingFieldValueError(ValueError):
    """A ``{fieldname}`` token whose field is empty in the document."""

    def __init__(self, fieldname: str) -> None:
        super().__init__(fieldname)
        self.fieldname = fieldname


def parse_pattern(pattern: str) -> list[Part]:
    """Parse a naming pattern into a list of literal strings and token tuples.

    Returns a list where each element is either:
      - a plain string (literal text)
      - a tuple ("counter", width) for counter tokens
      - a tuple ("YYYY"|"YY"|"MM"|"DD", 0) for date tokens
      - a tuple ("field", fieldname) for field tokens
    """
    parts: list[Part] = []
    last_end = 0

    for match in _TOKEN_RE.finditer(pattern):
        # Add any literal text before this token
        if match.start() > last_end:
            parts.append(pattern[last_end : match.start()])

        token = match.group(1) or match.group(2)
        if token.startswith("#"):
            parts.append(("counter", len(token)))
        elif token in _DATE_TOKENS:
            parts.append((token, 0))
        else:
            parts.append(("field", token))

        last_end = match.end()

    # Trailing literal text
    if last_end < len(pattern):
        parts.append(pattern[last_end:])

    return parts


def _render(part: tuple[str, int | str], now: date, values: dict[str, Any] | None) -> str:
    token, arg = part
    if token == "field":
        fieldname = str(arg)
        value = (values or {}).get(fieldname)
        text = "" if value is None else str(value).strip()
        if not text:
            raise MissingFieldValueError(fieldname)
        return text
    return _format_date_token(token, now)


def build_prefix(
    parts: list[Part], now: date | None = None, values: dict[str, Any] | None = None
) -> str:
    """Build the prefix part of a naming pattern (everything except the counter).

    This is used as the key for the counter in the naming_series table.
    Raises :class:`MissingFieldValueError` for an empty ``{field}`` before the counter.
    """
    if now is None:
        now = datetime.now(UTC)

    prefix_parts: list[str] = []
    for part in parts:
        if isinstance(part, str):
            prefix_parts.append(part)
        elif part[0] == "counter":
            break  # Stop at counter - prefix is everything before it
        else:
            prefix_parts.append(_render(part, now, values))

    return "".join(prefix_parts)


def format_name(
    parts: list[Part],
    counter: int,
    now: date | None = None,
    values: dict[str, Any] | None = None,
) -> str:
    """Format a complete name from parsed parts and a counter value.

    Raises :class:`MissingFieldValueError` for an empty ``{field}``.
    """
    if now is None:
        now = datetime.now(UTC)

    result: list[str] = []
    for part in parts:
        if isinstance(part, str):
            result.append(part)
        elif part[0] == "counter":
            result.append(str(counter).zfill(int(part[1])))
        else:
            result.append(_render(part, now, values))

    return "".join(result)


def has_counter(parts: list[Part]) -> bool:
    """Check if the pattern contains a counter token."""
    return any(isinstance(p, tuple) and p[0] == "counter" for p in parts)


def field_tokens(parts: list[Part]) -> list[str]:
    """The field names the pattern takes values from, in order."""
    return [str(p[1]) for p in parts if isinstance(p, tuple) and p[0] == "field"]


def resolve_simple(pattern: str, data: dict[str, Any]) -> str | None:
    """Resolve simple (non-counter) naming patterns.

    Returns None if the pattern requires a counter.
    """
    if pattern.startswith("field:"):
        field_name = pattern[6:]
        value = data.get(field_name)
        return str(value) if value else None

    if pattern == "hash":
        return uuid.uuid4().hex[:10]

    if pattern == "prompt":
        return str(data["name"]) if data.get("name") else None

    return None


def _format_date_token(token: str, now: date) -> str:
    if token == "YYYY":
        return str(now.year)
    if token == "YY":
        return str(now.year)[-2:]
    if token == "MM":
        return str(now.month).zfill(2)
    if token == "DD":
        return str(now.day).zfill(2)
    return ""
