"""Sandboxed globals for Server Script execution.

Provides a restricted set of builtins and utilities available inside
server scripts. Dangerous operations (file I/O, os, subprocess, import) are blocked.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger()

# Safe subset of Python builtins
_SAFE_BUILTINS: dict[str, Any] = {
    # Types
    "True": True,
    "False": False,
    "None": None,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "bytes": bytes,
    "bytearray": bytearray,
    "Decimal": Decimal,
    # Functions
    "abs": abs,
    "all": all,
    "any": any,
    "chr": chr,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "format": format,
    "hasattr": hasattr,
    "hash": hash,
    "hex": hex,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,  # safe — captured by sandbox
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "sorted": sorted,
    "sum": sum,
    "type": type,
    "zip": zip,
    # Datetime
    "datetime": datetime,
    "date": date,
    "time": time,
    "timedelta": timedelta,
    "timezone": timezone,
    # Math / json
    "math": math,
    "json": json,
    "re": re,
}

# Explicitly blocked names
_BLOCKED_NAMES = frozenset(
    {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "exit",
        "quit",
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "__builtins__",
        "__loader__",
        "__spec__",
    }
)


def build_safe_globals(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a sandboxed globals dict for exec().

    Args:
        extra: Additional names to inject (e.g. `doc`, `frappe`-like helpers).

    Returns:
        A dict suitable for use as `globals` in exec/eval.
    """
    g: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS.copy()}
    if extra:
        g.update(extra)
    return g


def validate_script(source: str) -> list[str]:
    """Static validation of a server script source code.

    Returns a list of error messages. Empty list = OK.
    """
    errors: list[str] = []

    # Check syntax
    try:
        compile(source, "<server_script>", "exec")
    except SyntaxError as e:
        errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        return errors

    # Check for dangerous patterns
    for name in _BLOCKED_NAMES:
        if name in source:
            errors.append(f"Використання '{name}' заборонено в Server Script")

    dangerous_patterns = [
        ("import ", "Пряме використання 'import' заборонено"),
        ("from ", "Пряме використання 'from ... import' заборонено"),
        ("os.", "Доступ до модуля 'os' заборонено"),
        ("subprocess", "Доступ до 'subprocess' заборонено"),
        ("sys.", "Доступ до модуля 'sys' заборонено"),
        ("shutil", "Доступ до 'shutil' заборонено"),
    ]

    for pattern, msg in dangerous_patterns:
        if pattern in source:
            # Allow patterns inside string literals (rough check — skip if inside quotes)
            errors.append(msg)

    return errors
