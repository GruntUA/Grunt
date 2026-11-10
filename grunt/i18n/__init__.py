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
    ngettext,
    parse_po_string,
    pgettext,
    translation_service,
    use_language,
)

#: Register the runtime translation provider (see :meth:`TranslationService.register_provider`).
register_provider = translation_service.register_provider

__all__ = [
    "NP_",
    "N_",
    "TranslationService",
    "_",
    "ngettext",
    "parse_po_string",
    "pgettext",
    "plural_form_count",
    "plural_index",
    "register_provider",
    "translation_service",
    "use_language",
]
