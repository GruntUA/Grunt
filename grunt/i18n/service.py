"""Translation service based on GNU gettext (PO/POT files).

Provides `_()` and `ngettext()` for translating server-side messages.
Translations are resolved in this order:
1. a registered runtime provider (e.g. the Translate app - DB-backed, editable
   without a redeploy); see :func:`register_provider`
2. PO files in this module's ``locales/`` dir and every installed app's
   ``<module>/locales/`` dir

English strings are the source keys. The fallback language (no request, or
nothing negotiable) is the site default - ``SystemSettings.language``, seeded at
startup via :meth:`TranslationService.set_default`; ``uk`` until then.

Usage:
    from grunt.i18n import _, ngettext

    _("Document not found")
    _("Field '%(field)s' is required") % {"field": "name"}
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
"""

from __future__ import annotations

import gettext as _gettext
import secrets
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import TYPE_CHECKING

import grunt
from grunt.i18n.plurals import plural_index
from grunt.log import log

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


# Directory containing locale files (uk/LC_MESSAGES/grunt.po)
_LOCALE_DIR = Path(__file__).parent / "locales"

# Per-request language (set by middleware); None -> the site default below.
_current_lang: ContextVar[str | None] = ContextVar("grunt_lang", default=None)

# Fallback language outside a request (tasks, CLI) and when negotiation fails.
_default_lang: str = "uk"

# Cached gettext translation objects: {lang: GNUTranslations}
_translations: dict[str, _gettext.GNUTranslations | _gettext.NullTranslations] = {}

# Flattened per-locale catalogs merged from every installed app's locales/ dir.
# Keys are bare source strings, or "context|msgid" for context-aware entries.
_app_catalogs: dict[str, dict[str, str]] = {}

# Optional runtime provider: given a locale, returns {source | "ctx|msg": translated}.
# Registered by an app (see register_provider); consulted before any PO file.
_provider: Callable[[str], dict[str, str]] | None = None
_provider_cache: dict[str, dict[str, str]] = {}

# Cheap version tag for the frontend bundle - changes on any provider
# invalidation, app-catalog reload, or active-language change.
_catalog_version: str = "0"

# Languages the request-language negotiator accepts. Seeded from the source (en)
# and default (uk); widened at startup from active geo.Language rows.
_DEFAULT_SUPPORTED = frozenset({"uk", "en"})
_supported: set[str] = set(_DEFAULT_SUPPORTED)

# UI languages (the language switcher): the English source, the site default,
# every locale that has a PO catalog (core or any app), plus extras a runtime
# provider declares (e.g. the Translate app's enabled locales). Discovery is
# cached until reload()/invalidate().
_ui_langs_cache: list[str] | None = None
_extra_ui_langs: set[str] = set()
# Native language names ({"uk": "Українська"}), seeded from geo.Language.
_language_names: dict[str, str] = {}


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
            log.debug("i18n.loaded_mo", lang=lang)
            return trans

    # Fall back to parsing .po file manually
    po_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "grunt.po"
    if po_path.exists():
        catalog = _parse_po_file(po_path)
        trans = _DictTranslations(catalog, lang)
        _translations[lang] = trans
        log.debug("i18n.loaded_po", lang=lang, entries=len(catalog))
        return trans

    # No translation file - return NullTranslations (passthrough)
    trans = _gettext.NullTranslations()
    _translations[lang] = trans
    return trans


def _parse_po_file(path: Path) -> dict[str, str]:
    """Parse a PO *file*. See :func:`parse_po_string` for the format notes."""
    with open(path, encoding="utf-8") as f:
        return parse_po_string(f.read())


def parse_po_string(text: str) -> dict[str, str]:
    """Parse PO text into msgid -> msgstr mappings (via polib).

    Keys: bare ``msgid``, ``"<msgctxt>\\x04<msgid>"`` with context, and
    ``"<key>\\x00<n>"`` for plural forms (plus the bare key -> form 0).
    Multi-line (wrapped) strings are joined; obsolete, fuzzy and untranslated
    entries are skipped - the same set ``msgfmt`` would compile.
    """
    import polib

    catalog: dict[str, str] = {}
    for entry in polib.pofile(text):
        if entry.obsolete or entry.fuzzy or not entry.msgid:
            continue
        key = f"{entry.msgctxt}\x04{entry.msgid}" if entry.msgctxt else entry.msgid
        if entry.msgid_plural:
            for idx, form in sorted(entry.msgstr_plural.items()):
                if form:
                    catalog[f"{key}\x00{idx}"] = form
            if entry.msgstr_plural.get(0):
                catalog[key] = entry.msgstr_plural[0]
        elif entry.msgstr:
            catalog[key] = entry.msgstr
    return catalog


def _flatten_catalog(catalog: dict[str, str]) -> dict[str, str]:
    """Render context entries as ``"context|msgid"``; keep plural keys
    (``"...\\x00<n>"``) so ``ngettext`` and the frontend bundle can use them."""
    flat: dict[str, str] = {}
    for key, value in catalog.items():
        if "\x04" in key:
            ctx, rest = key.split("\x04", 1)
            flat[f"{ctx}|{rest}"] = value
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


def _app_locale_codes() -> set[str]:
    """Locale codes of every installed app's PO files."""
    try:
        from grunt.site.manager import site_manager

        apps_dir = site_manager.bench_dir / "apps"
    except Exception:
        return set()
    if not apps_dir.is_dir():
        return set()
    codes = {p.stem for p in apps_dir.glob("*/*/locales/*.po")}
    codes.update(p.parent.parent.name for p in apps_dir.glob("*/*/locales/*/LC_MESSAGES/*.po"))
    return {normalize_lang(c) for c in codes}


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
            log.warning("i18n.app_po_parse_error", path=str(po))
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
        log.exception("i18n.provider_error", lang=lang)
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

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        idx = plural_index(self._lang, n)
        result = self._catalog.get(f"{msgid1}\x00{idx}")
        if result:
            return result
        return msgid1 if n == 1 else msgid2

    def pgettext(self, context: str, message: str) -> str:
        key = f"{context}\x04{message}"
        return self._catalog.get(key, message)


class TranslationService:
    """Manages translations for backend strings."""

    def get_lang(self) -> str:
        return _current_lang.get() or _default_lang

    def set_lang(self, lang: str) -> Token[str | None]:
        """Set the current language. Returns a token for reset."""
        return _current_lang.set(lang)

    @contextmanager
    def use_language(self, lang: str | None) -> Iterator[None]:
        """Temporarily switch the language, e.g. to render mail in the recipient's.

        *lang* may be a locale tag (``en-US``); empty/unsupported -> unchanged.
        """
        code = normalize_lang(lang)
        if not code or code not in _supported:
            yield
            return
        token = _current_lang.set(code)
        try:
            yield
        finally:
            _current_lang.reset(token)

    def default_lang(self) -> str:
        return _default_lang

    def set_default(self, lang: str | None) -> None:
        """Set the site default language (``SystemSettings.language``)."""
        global _default_lang, _ui_langs_cache
        code = normalize_lang(lang)
        if code and code != _default_lang:
            _default_lang = code
            _supported.add(code)
            _ui_langs_cache = None
            self._bump_version()

    def translate(self, source: str, lang: str | None = None) -> str:
        """Translate a source string: provider -> app PO -> core PO -> source.

        No language is special-cased: source strings in this codebase are a mix
        of English (framework msgids) and Ukrainian (DocType labels), so every
        locale - ``en`` included - is looked up and falls back to the source.
        """
        lang = lang or self.get_lang()

        hit = _provider_catalog(lang).get(source) or _app_catalog(lang).get(source)
        if hit:
            return hit

        return _load_translations(lang).gettext(source)

    def ngettext(self, singular: str, plural: str, n: int, lang: str | None = None) -> str:
        """Translate with plural forms: provider -> app PO -> core PO -> fallback.

        Plural forms are stored as flat keys ``"<singular>\\x00<form-index>"``
        (same convention the PO parser uses).
        """
        lang = lang or self.get_lang()

        key = f"{singular}\x00{plural_index(lang, n)}"
        hit = _provider_catalog(lang).get(key) or _app_catalog(lang).get(key)
        if hit:
            return hit

        result = _load_translations(lang).ngettext(singular, plural, n)
        if result not in (singular, plural):
            return result
        return singular if abs(n) == 1 else plural

    def pgettext(self, context: str, message: str, lang: str | None = None) -> str:
        """Translate with context (msgctxt).

        Order: contextual entry (provider -> app -> core PO) -> **plain** entry for
        the same string (so ``Назва`` -> ``Name`` need only be translated once,
        not per ``meta:<DocType>.<field>`` context) -> the source message.
        """
        lang = lang or self.get_lang()

        flat = f"{context}|{message}"
        hit = _provider_catalog(lang).get(flat) or _app_catalog(lang).get(flat)
        if hit:
            return hit

        trans = _load_translations(lang)
        if hasattr(trans, "pgettext"):
            ctx_hit = trans.pgettext(context, message)
            if ctx_hit != message:
                return ctx_hit

        # Fall back to a context-free translation of the same string.
        return self.translate(message, lang)

    def get_all_translations(self, lang: str) -> dict[str, str]:
        """Full flat catalog for a language (for the frontend JSON bundle).

        Merge order (later wins): core PO -> installed apps' PO -> runtime provider.
        Keys are bare source strings or ``"context|msgid"``.
        """
        trans = _load_translations(lang)
        result: dict[str, str] = {}
        if isinstance(trans, _DictTranslations):
            result.update(_flatten_catalog(trans._catalog))
        result.update(_app_catalog(lang))
        result.update(_provider_catalog(lang))
        return result

    # Runtime provider / cache management

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
        log.debug("i18n.provider_registered", provider=getattr(fn, "__qualname__", repr(fn)))

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

    # Supported languages (request-language negotiation)

    def supported_langs(self) -> set[str]:
        return set(_supported) | set(self.ui_languages())

    def ui_languages(self) -> list[str]:
        """Languages the UI can be switched to (sorted; the source ``en`` included)."""
        global _ui_langs_cache
        if _ui_langs_cache is None:
            codes = {"en", _default_lang, *_extra_ui_langs}
            codes.update(p.parent.parent.name for p in _LOCALE_DIR.glob("*/LC_MESSAGES/*.po"))
            codes.update(_app_locale_codes())
            _ui_langs_cache = sorted(c for c in codes if c)
        return list(_ui_langs_cache)

    def add_ui_languages(self, codes: object) -> None:
        """Offer extra UI languages that have no PO file (yet) - e.g. locales
        translated only in the database by a runtime provider."""
        global _ui_langs_cache
        try:
            new = {normalize_lang(str(c)) for c in codes if c}  # type: ignore[union-attr]
        except TypeError:
            return
        new.discard("")
        if not new <= _extra_ui_langs:
            _extra_ui_langs.update(new)
            _ui_langs_cache = None
            self._bump_version()

    def set_language_names(self, names: dict[str, str]) -> None:
        """Native names for the language switcher (``{"uk": "Українська"}``)."""
        _language_names.update({k: v for k, v in names.items() if k and v})

    def language_name(self, code: str) -> str:
        return _language_names.get(code) or code

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
            log.debug("i18n.supported_langs", langs=sorted(_supported))

    def reload(self) -> None:
        """Clear every cache (forces reload from files / provider)."""
        global _ui_langs_cache
        _ui_langs_cache = None
        _translations.clear()
        _app_catalogs.clear()
        _provider_cache.clear()
        self._bump_version()


async def language_of(user: str | None) -> str | None:
    """Stored UI language of *user* (email) - render mail/notifications to them in it.

    Pair with :func:`use_language`; ``None`` (unknown user / no preference) keeps
    the current language.
    """
    if not user:
        return None

    try:
        return await grunt.db.get_value("User", user, "language")
    except Exception:  # noqa: BLE001 - a missing user must not break delivery
        return None


def normalize_lang(lang: str | None) -> str:
    """``"uk-UA"`` / ``"EN_us"`` -> ``"uk"`` / ``"en"``; empty -> ``""``."""
    return (lang or "").strip().lower()[:2]


# Module-level singleton and convenience functions
translation_service = TranslationService()
use_language = translation_service.use_language


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


def N_(message: str) -> str:  # noqa: N802 - gettext convention
    """Mark *message* for extraction without translating it (gettext_noop).

    For module-level constants, translated later where used: ``_(CONST)``.
    """
    return message


def NP_(context: str, message: str) -> str:  # noqa: N802
    """Contextual :func:`N_` - translate later with ``pgettext(context, CONST)``."""
    return message
