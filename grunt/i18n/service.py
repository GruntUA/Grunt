"""Translation service based on GNU gettext (PO/POT files).

Provides `_()` and `ngettext()` for translating server-side messages.
Translations are resolved in this order:
1. a registered runtime provider (e.g. the Translate app — DB-backed, editable
   without a redeploy); see :func:`register_provider`
2. PO files in this module's ``locales/`` dir and every installed app's
   ``<module>/locales/`` dir

Default language is Ukrainian (uk). English strings are the source keys.

Usage:
    from grunt.i18n import _, ngettext

    _("Document not found")
    _("Field '%(field)s' is required") % {"field": "name"}
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
"""

from __future__ import annotations

import gettext as _gettext
import secrets
from contextvars import ContextVar, Token
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()

# Directory containing locale files (uk/LC_MESSAGES/grunt.po)
_LOCALE_DIR = Path(__file__).parent / "locales"

# Per-request language (set by middleware, default: uk)
_current_lang: ContextVar[str] = ContextVar("grunt_lang", default="uk")

# Cached gettext translation objects: {lang: GNUTranslations}
_translations: dict[str, _gettext.GNUTranslations | _gettext.NullTranslations] = {}

# Flattened per-locale catalogs merged from every installed app's locales/ dir.
# Keys are bare source strings, or "context|msgid" for context-aware entries.
_app_catalogs: dict[str, dict[str, str]] = {}

# Optional runtime provider: given a locale, returns {source | "ctx|msg": translated}.
# Registered by an app (see register_provider); consulted before any PO file.
_provider: Callable[[str], dict[str, str]] | None = None
_provider_cache: dict[str, dict[str, str]] = {}

# Cheap version tag for the frontend bundle — changes on any provider
# invalidation, app-catalog reload, or active-language change.
_catalog_version: str = "0"

# Languages the request-language negotiator accepts. Seeded from the source (en)
# and default (uk); widened at startup from active geo.Language rows.
_DEFAULT_SUPPORTED = frozenset({"uk", "en"})
_supported: set[str] = set(_DEFAULT_SUPPORTED)


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
            trans: _gettext.GNUTranslations | _gettext.NullTranslations = _gettext.GNUTranslations(
                f
            )
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


def _flatten_catalog(catalog: dict[str, str]) -> dict[str, str]:
    """Drop internal plural keys; render context entries as ``"context|msgid"``."""
    flat: dict[str, str] = {}
    for key, value in catalog.items():
        if "\x00" in key:
            continue
        if "\x04" in key:
            ctx, msgid = key.split("\x04", 1)
            flat[f"{ctx}|{msgid}"] = value
        else:
            flat[key] = value
    return flat


def _app_locale_po_files(lang: str) -> list[Path]:
    """Every installed app's PO file for *lang* (``apps/*/*/locales/<lang>.po``)."""
    try:
        from grunt.site.manager import site_manager

        apps_dir = site_manager.bench_dir / "apps"
    except Exception:
        return []
    if not apps_dir.is_dir():
        return []
    files = list(apps_dir.glob(f"*/*/locales/{lang}.po"))
    files += list(apps_dir.glob(f"*/*/locales/{lang}/LC_MESSAGES/*.po"))
    return files


def _app_catalog(lang: str) -> dict[str, str]:
    """Merged, flattened catalog from every installed app's PO file for *lang*."""
    cached = _app_catalogs.get(lang)
    if cached is not None:
        return cached
    merged: dict[str, str] = {}
    for po in _app_locale_po_files(lang):
        try:
            merged.update(_flatten_catalog(_parse_po_file(po)))
        except Exception:
            logger.warning("i18n.app_po_parse_error", path=str(po))
    _app_catalogs[lang] = merged
    return merged


def _provider_catalog(lang: str) -> dict[str, str]:
    """Cached result of the registered runtime provider for *lang* (or ``{}``)."""
    if _provider is None:
        return {}
    cached = _provider_cache.get(lang)
    if cached is not None:
        return cached
    try:
        result = dict(_provider(lang) or {})
    except Exception:
        logger.exception("i18n.provider_error", lang=lang)
        result = {}
    _provider_cache[lang] = result
    return result


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

    def set_lang(self, lang: str) -> Token[str]:
        """Set the current language. Returns a token for reset."""
        return _current_lang.set(lang)

    def translate(self, source: str, lang: str | None = None) -> str:
        """Translate a source string: provider → app PO → core PO → source."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return source

        hit = _provider_catalog(lang).get(source) or _app_catalog(lang).get(source)
        if hit:
            return hit

        return _load_translations(lang).gettext(source)

    def ngettext(self, singular: str, plural: str, n: int, lang: str | None = None) -> str:
        """Translate with plural forms."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return singular if n == 1 else plural

        trans = _load_translations(lang)
        return trans.ngettext(singular, plural, n)

    def pgettext(self, context: str, message: str, lang: str | None = None) -> str:
        """Translate with context (msgctxt): provider → app PO → core PO → message."""
        lang = lang or _current_lang.get()

        if lang == "en":
            return message

        flat = f"{context}|{message}"
        hit = _provider_catalog(lang).get(flat) or _app_catalog(lang).get(flat)
        if hit:
            return hit

        trans = _load_translations(lang)
        if hasattr(trans, "pgettext"):
            return trans.pgettext(context, message)
        return message

    def get_all_translations(self, lang: str) -> dict[str, str]:
        """Full flat catalog for a language (for the frontend JSON bundle).

        Merge order (later wins): core PO → installed apps' PO → runtime provider.
        Keys are bare source strings or ``"context|msgid"``.
        """
        trans = _load_translations(lang)
        result: dict[str, str] = {}
        if isinstance(trans, _DictTranslations):
            result.update(_flatten_catalog(trans._catalog))
        result.update(_app_catalog(lang))
        result.update(_provider_catalog(lang))
        return result

    # ── Runtime provider / cache management ──────────────────────────────

    def register_provider(self, fn: Callable[[str], dict[str, str]]) -> None:
        """Register the runtime translation provider (one; last registration wins).

        *fn* takes a locale and returns ``{source | "ctx|msg": translated}``. It is
        consulted before any PO file and its result is cached per locale until
        :meth:`invalidate` is called.
        """
        global _provider
        _provider = fn
        _provider_cache.clear()
        self._bump_version()
        logger.info("i18n.provider_registered", provider=getattr(fn, "__qualname__", repr(fn)))

    def invalidate(self, lang: str | None = None) -> None:
        """Drop cached provider/app catalogs (all locales, or just *lang*)."""
        if lang is None:
            _provider_cache.clear()
            _app_catalogs.clear()
        else:
            _provider_cache.pop(lang, None)
            _app_catalogs.pop(lang, None)
        self._bump_version()

    def catalog_version(self, lang: str | None = None) -> str:
        """Opaque tag that changes whenever any effective catalog changes."""
        return _catalog_version

    def _bump_version(self) -> None:
        global _catalog_version
        _catalog_version = secrets.token_hex(8)

    # ── Supported languages (request-language negotiation) ───────────────

    def supported_langs(self) -> set[str]:
        return set(_supported)

    def set_supported(self, codes: object) -> None:
        """Set the accepted language set (``en``/``uk`` are always kept)."""
        global _supported
        try:
            incoming = {str(c)[:2].lower() for c in codes if c}  # type: ignore[union-attr]
        except TypeError:
            incoming = set()
        new = incoming | set(_DEFAULT_SUPPORTED)
        if new != _supported:
            _supported = new
            self._bump_version()
            logger.info("i18n.supported_langs", langs=sorted(_supported))

    def reload(self) -> None:
        """Clear every cache (forces reload from files / provider)."""
        _translations.clear()
        _app_catalogs.clear()
        _provider_cache.clear()
        self._bump_version()


# Module-level singleton and convenience functions
translation_service = TranslationService()


def _(source: str) -> str:
    """Translate a string using the current language.

    Usage:
        from grunt.i18n import _
        message = _("Document not found")
    """
    return translation_service.translate(source)


def ngettext(singular: str, plural: str, n: int) -> str:
    """Translate with plural forms.

    Usage:
        from grunt.i18n import ngettext
        msg = ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
    """
    return translation_service.ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    """Translate with context.

    Usage:
        from grunt.i18n import pgettext
        label = pgettext("button", "Save")  # "Зберегти"
    """
    return translation_service.pgettext(context, message)
