"""Naming pattern parser and formatter.

Supported patterns:
  - "field:title"           → value of the 'title' field
  - "hash"                  → short UUID (first 10 chars)
  - "prompt"                → user must supply 'name' in data
  - "PREFIX-.YYYY.-.####"   → pattern-based with counter
  - "INV-.MM.-.YYYY.-.#####" → any combination of tokens

Pattern tokens:
  .YYYY.  → 4-digit year
  .YY.    → 2-digit year
  .MM.    → 2-digit month
  .DD.    → 2-digit day
  .####.  → zero-padded counter (width = number of #)
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

# Regex to find .TOKEN. placeholders in the pattern.
# The trailing dot is optional so tokens can appear at end of string (e.g. "INV-.####")
_TOKEN_RE = re.compile(r"\.(#+|YYYY|YY|MM|DD)\.?")


def parse_pattern(pattern: str) -> list[str | tuple[str, int]]:
    """Parse a naming pattern into a list of literal strings and token tuples.

    Returns a list where each element is either:
      - a plain string (literal text)
      - a tuple ("counter", width) for counter tokens
      - a tuple ("YYYY"|"YY"|"MM"|"DD", 0) for date tokens
    """
    parts: list[str | tuple[str, int]] = []
    last_end = 0

    for match in _TOKEN_RE.finditer(pattern):
        # Add any literal text before this token
        if match.start() > last_end:
            parts.append(pattern[last_end : match.start()])

        token = match.group(1)
        if token.startswith("#"):
            parts.append(("counter", len(token)))
        else:
            parts.append((token, 0))

        last_end = match.end()

    # Trailing literal text
    if last_end < len(pattern):
        parts.append(pattern[last_end:])

    return parts


def build_prefix(parts: list[str | tuple[str, int]], now: datetime | None = None) -> str:
    """Build the prefix part of a naming pattern (everything except the counter).

    This is used as the key for the counter in the naming_series table.
    """
    if now is None:
        now = datetime.now(UTC)

    prefix_parts: list[str] = []
    for part in parts:
        if isinstance(part, str):
            prefix_parts.append(part)
        else:
            token, width = part
            if token == "counter":
                break  # Stop at counter — prefix is everything before it
            prefix_parts.append(_format_date_token(token, now))

    return "".join(prefix_parts)


def format_name(
    parts: list[str | tuple[str, int]], counter: int, now: datetime | None = None
) -> str:
    """Format a complete name from parsed parts and a counter value."""
    if now is None:
        now = datetime.now(UTC)

    result: list[str] = []
    for part in parts:
        if isinstance(part, str):
            result.append(part)
        else:
            token, width = part
            if token == "counter":
                result.append(str(counter).zfill(width))
            else:
                result.append(_format_date_token(token, now))

    return "".join(result)


def has_counter(parts: list[str | tuple[str, int]]) -> bool:
    """Check if the pattern contains a counter token."""
    return any(isinstance(p, tuple) and p[0] == "counter" for p in parts)


def resolve_simple(pattern: str, data: dict[str, Any]) -> str | None:
    """Resolve simple (non-counter) naming patterns.

    Returns None if the pattern requires a counter.
    """
    if pattern.startswith("field:"):
        field_name = pattern[6:]
        value = data.get(field_name)
        return str(value) if value else None

    if pattern == "hash":
        import uuid

        return uuid.uuid4().hex[:10]

    if pattern == "prompt":
        return str(data["name"]) if data.get("name") else None

    return None


def _format_date_token(token: str, now: datetime) -> str:
    if token == "YYYY":
        return str(now.year)
    if token == "YY":
        return str(now.year)[-2:]
    if token == "MM":
        return str(now.month).zfill(2)
    if token == "DD":
        return str(now.day).zfill(2)
    return ""
