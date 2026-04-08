"""Translation service based on GNU gettext (PO/POT files).

Provides `_()` and `ngettext()` for translating server-side messages.
Translations are loaded from:
1. PO/MO files in locales/ directory (compiled via `msgfmt` or loaded raw)
2. GruntTranslation table (user/app-supplied overrides)

Default language is Ukrainian (uk). English strings are the source keys.

Usage:
    from grunt.core.i18n import _, ngettext

    _("Document not found")
    _("Field '%(field)s' is required") % {"field": "name"}
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
"""

from __future__ import annotations

import gettext as _gettext
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Directory containing locale files (uk/LC_MESSAGES/grunt.po)
_LOCALE_DIR = Path(__file__).parent / "locales"

# Per-request language (set by middleware, default: uk)
_current_lang: ContextVar[str] = ContextVar("grunt_lang", default="uk")

# Cached gettext translation objects: {lang: GNUTranslations}
_translations: dict[str, _gettext.GNUTranslations | _gettext.NullTranslations] = {}

# Runtime overrides loaded from DB
_db_overrides: dict[str, dict[str, str]] = {}


def _load_translations(lang: str) -> _gettext.GNUTranslations | _gettext.NullTranslations:
    """Load gettext translations for a language.

    Tries .mo first (compiled), then falls back to parsing .po directly.
    """
    if lang in _translations:
        return _translations[lang]

    # Try compiled .mo file first
    mo_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "grunt.mo"
    if mo_path.exists():
        with open(mo_path, "rb") as f:
            trans = _gettext.GNUTranslations(f)
            _translations[lang] = trans
            logger.debug("i18n.loaded_mo", lang=lang)
            return trans

    # Fall back to parsing .po file manually
    po_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "grunt.po"
    if po_path.exists():
        catalog = _parse_po_file(po_path)
        trans = _DictTranslations(catalog, lang)
        _translations[lang] = trans
        logger.debug("i18n.loaded_po", lang=lang, entries=len(catalog))
        return trans

    # No translation file — return NullTranslations (passthrough)
    trans = _gettext.NullTranslations()
    _translations[lang] = trans
    return trans


def _parse_po_file(path: Path) -> dict[str, str]:
    """Simple PO file parser — extracts msgid → msgstr mappings.

    Handles: simple strings, msgctxt, msgid_plural (stores msgstr[0..N]).
    Does NOT handle: multiline msgid with concatenation, obsolete entries.
    """
    catalog: dict[str, str] = {}
    current_msgctxt: str | None = None
    current_msgid: str | None = None
    current_msgid_plural: str | None = None
    current_msgstr: str | None = None
    plural_forms: dict[int, str] = {}

    def _flush() -> None:
        nonlocal current_msgctxt, current_msgid, current_msgid_plural, current_msgstr, plural_forms
        if current_msgid is not None and current_msgid != "":
            key = current_msgid
            if current_msgctxt:
                key = f"{current_msgctxt}\x04{current_msgid}"

            if current_msgid_plural and plural_forms:
                # Store plural forms as msgstr[0], msgstr[1], etc.
                for idx, form in sorted(plural_forms.items()):
                    if form:
                        catalog[f"{key}\x00{idx}"] = form
                # Also store the singular form
                if plural_forms.get(0):
                    catalog[key] = plural_forms[0]
            elif current_msgstr:
                catalog[key] = current_msgstr

        current_msgctxt = None
        current_msgid = None
        current_msgid_plural = None
        current_msgstr = None
        plural_forms = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("msgctxt "):
                _flush()
                current_msgctxt = _unquote(line[8:])
            elif line.startswith("msgid_plural "):
                current_msgid_plural = _unquote(line[13:])
            elif line.startswith("msgid "):
                if current_msgid is not None:
                    _flush()
                current_msgid = _unquote(line[6:])
            elif line.startswith("msgstr["):
                idx = int(line[7])
                value = _unquote(line[10:])
                plural_forms[idx] = value
            elif line.startswith("msgstr "):
                current_msgstr = _unquote(line[7:])

        _flush()

    return catalog


def _unquote(s: str) -> str:
    """Remove surrounding quotes from a PO string value."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.replace("\\n", "\n").replace('\\"', '"')


class _DictTranslations(_gettext.NullTranslations):
    """gettext-compatible translations backed by a dict from PO parsing."""

    def __init__(self, catalog: dict[str, str], lang: str) -> None:
        super().__init__()
        self._catalog = catalog
        self._lang = lang

    def gettext(self, message: str) -> str:
        return self._catalog.get(message, message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        idx = self._plural_index(n)
        key = f"{singular}\x00{idx}"
        result = self._catalog.get(key)
        if result:
            return result
        return singular if n == 1 else plural

    def pgettext(self, context: str, message: str) -> str:
        key = f"{context}\x04{message}"
        return self._catalog.get(key, message)

    def _plural_index(self, n: int) -> int:
        """Ukrainian plural form: 3 forms."""
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and (n % 100 < 12 or n % 100 > 14):
            return 1
        return 2


class TranslationService:
    """Manages translations for backend strings."""

    def get_lang(self) -> str:
        return _current_lang.get()

    def set_lang(self, lang: str) -> str:
        """Set the current language. Returns a token for reset."""
        return _current_lang.set(lang)

    def translate(self, source: str, lang: str | None = None) -> str:
        """Translate a source string via gettext."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return source

        # Check DB overrides first
        override = _db_overrides.get(lang, {}).get(source)
        if override:
            return override

        trans = _load_translations(lang)
        return trans.gettext(source)

    def ngettext(self, singular: str, plural: str, n: int, lang: str | None = None) -> str:
        """Translate with plural forms."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return singular if n == 1 else plural

        trans = _load_translations(lang)
        return trans.ngettext(singular, plural, n)

    def pgettext(self, context: str, message: str, lang: str | None = None) -> str:
        """Translate with context (msgctxt)."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return message

        trans = _load_translations(lang)
        if hasattr(trans, "pgettext"):
            return trans.pgettext(context, message)
        return message

    async def load_overrides_from_db(self, session: Any) -> int:
        """Load translation overrides from Translation DocType table."""
        try:
            from sqlalchemy import select  # noqa: PLC0415

            from grunt.core.metadata.compiler import compile_doctype_to_table  # noqa: PLC0415
            from grunt.core.metadata.registry import doctype_registry  # noqa: PLC0415

            table = compile_doctype_to_table(doctype_registry._doctypes["Translation"])
            result = await session.execute(select(table))
            rows = result.mappings().all()

            count = 0
            for row in rows:
                lang = row["language"]
                if lang not in _db_overrides:
                    _db_overrides[lang] = {}
                _db_overrides[lang][row["source"]] = row["translated"]
                count += 1

            logger.info("i18n.db_overrides_loaded", count=count)
            return count
        except Exception:  # noqa: BLE001
            logger.debug("i18n.db_load_skipped", reason="table may not exist yet")
            return 0

    def get_all_translations(self, lang: str) -> dict[str, str]:
        """Get all translations for a language (for frontend JSON export).

        Returns a flat dict: {source: translated}.
        """
        trans = _load_translations(lang)
        result: dict[str, str] = {}

        if isinstance(trans, _DictTranslations):
            # Filter out internal plural keys
            for key, value in trans._catalog.items():
                if "\x00" not in key and "\x04" not in key:
                    result[key] = value
                elif "\x04" in key:
                    # Include context entries as "context|msgid"
                    ctx, msgid = key.split("\x04", 1)
                    result[f"{ctx}|{msgid}"] = value

        # Apply DB overrides
        result.update(_db_overrides.get(lang, {}))
        return result

    def reload(self) -> None:
        """Clear cached translations (forces reload from files)."""
        _translations.clear()


# Module-level singleton and convenience functions
translation_service = TranslationService()


def _(source: str) -> str:
    """Translate a string using the current language.

    Usage:
        from grunt.core.i18n import _
        message = _("Document not found")
    """
    return translation_service.translate(source)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Translate with plural forms.

    Usage:
        from grunt.core.i18n import ngettext
        msg = ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
    """
    return translation_service.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    """Translate with context.

    Usage:
        from grunt.core.i18n import pgettext
        label = pgettext("button", "Save")  # "Зберегти"
    """
    return translation_service.pgettext(context, message)
