"""Plural-form rules shared by the runtime, the bundle and the extractor.

Each language maps to ``(form_count, index_fn)`` where ``index_fn(n)`` returns
the 0-based form to use for cardinal ``n``. English has 2 forms (one / other);
Ukrainian, Russian and Polish have the classic Slavic 3.
"""

from __future__ import annotations

from collections.abc import Callable

DEFAULT_LANG = "en"


def _slavic3(n: int) -> int:
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


def _english(n: int) -> int:
    return 0 if n == 1 else 1


_RULES: dict[str, tuple[int, Callable[[int], int]]] = {
    "en": (2, _english),
    "uk": (3, _slavic3),
    "ru": (3, _slavic3),
    "pl": (3, _slavic3),
    "cs": (3, _slavic3),
    "sk": (3, _slavic3),
}


def plural_form_count(lang: str) -> int:
    return _RULES.get(lang, _RULES[DEFAULT_LANG])[0]


def plural_index(lang: str, n: int) -> int:
    return _RULES.get(lang, _RULES[DEFAULT_LANG])[1](abs(int(n)))
