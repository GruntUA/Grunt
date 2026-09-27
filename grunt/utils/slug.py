"""URL slugs — Cyrillic transliterated by the KMU 55/2010 table, then ``[a-z0-9-]+``."""

from __future__ import annotations

import re

# fmt: off
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia", "'": "", "’": "",
    "ё": "e", "э": "e", "ы": "y", "ъ": "",
}
# fmt: on
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Transliterate *text* to a lowercase ``[a-z0-9-]+`` URL slug."""
    lowered = text.lower()
    transliterated = "".join(_TRANSLIT.get(ch, ch) for ch in lowered)
    slug = _NON_SLUG_RE.sub("-", transliterated).strip("-")
    return slug or "item"
