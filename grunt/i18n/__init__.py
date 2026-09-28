"""Internationalization module for Grunt backend (GNU gettext / PO/POT).

Usage:
    from grunt.i18n import _, ngettext, pgettext

    _("Document not found")
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
    pgettext("button", "Save")
"""

from grunt.i18n.plurals import plural_form_count, plural_index
from grunt.i18n.service import (
    N_,
    NP_,
    TranslationService,
    _,
    language_of,
    ngettext,
    parse_po_string,
    pgettext,
    translation_service,
    use_language,
)

#: Register the runtime translation provider (see :meth:`TranslationService.register_provider`).
register_provider = translation_service.register_provider

#: Dynamic-options source for language Select fields (User.language,
#: SystemSettings.language): the UI languages, labelled with native names.
LANGUAGE_OPTIONS_SOURCE = "grunt.i18n.language"


def _language_options() -> list[str | tuple[str, str]]:
    return [(c, translation_service.language_name(c)) for c in translation_service.ui_languages()]


def _register_language_options() -> None:
    from grunt.metadata.dynamic_options import register_option_provider

    register_option_provider(LANGUAGE_OPTIONS_SOURCE, _language_options)


_register_language_options()

__all__ = [
    "LANGUAGE_OPTIONS_SOURCE",
    "NP_",
    "N_",
    "TranslationService",
    "_",
    "language_of",
    "ngettext",
    "parse_po_string",
    "pgettext",
    "plural_form_count",
    "plural_index",
    "register_provider",
    "translation_service",
    "use_language",
]
