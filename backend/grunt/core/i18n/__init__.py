"""Internationalization module for Grunt backend (GNU gettext / PO/POT).

Usage:
    from grunt.core.i18n import _, ngettext, pgettext

    _("Document not found")
    ngettext("%(count)d document", "%(count)d documents", count) % {"count": count}
    pgettext("button", "Save")
"""

from grunt.core.i18n.service import TranslationService, _, ngettext, pgettext, translation_service

__all__ = ["TranslationService", "_", "ngettext", "pgettext", "translation_service"]
