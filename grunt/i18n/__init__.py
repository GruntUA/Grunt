"""Internationalization module for Grunt backend (GNU gettext / PO/POT).

Usage:
    from grunt.i18n import _, ngettext, pgettext

    _("Document not found")
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
    pgettext("button", "Save")
"""

from grunt.i18n.service import TranslationService, _, ngettext, pgettext, translation_service

#: Register the runtime translation provider (see :meth:`TranslationService.register_provider`).
register_provider = translation_service.register_provider

__all__ = [
    "TranslationService",
    "_",
    "ngettext",
    "pgettext",
    "register_provider",
    "translation_service",
]
