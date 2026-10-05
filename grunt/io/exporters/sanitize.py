"""Guards against CSV/Excel formula injection (CWE-1236) in exported values.

A string cell value that happens to start with ``=``, ``+``, ``-``, ``@``
(or a leading tab/CR used to sneak past a naive check for those) is
auto-interpreted as a *live formula* by Excel/LibreOffice/Sheets when the
exported file is later opened - regardless of whether the export format is
.csv or .xlsx. Verified live: ``openpyxl`` sets ``cell.data_type = "f"`` for
a plain string value starting with ``=``, meaning any document field under
attacker control (any regular text field an authenticated user can set)
becomes formula execution - data exfiltration via ``=HYPERLINK(...)``, or
worse, in whoever's spreadsheet application opens the export.
"""

from __future__ import annotations

_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def escape_formula(value: str) -> str:
    """Prefix *value* with a single quote if it would be auto-interpreted
    as a formula by spreadsheet software, otherwise return it unchanged.

    A leading ``'`` is the standard Excel-recognized "force text" escape -
    it is not itself rendered, and it's what Excel's own "keep leading
    apostrophe" convention already relies on.
    """
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return f"'{value}"
    return value
