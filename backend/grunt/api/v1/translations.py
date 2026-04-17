from __future__ import annotations

from typing import Any

import grunt


@grunt.whitelist(allow_guest=True)
async def get_translations(locale: str) -> dict[str, Any]:
    """Return all translations for a locale as a flat JSON dict.

    Call via: /api/v1/method/grunt.api.v1.translations.get_translations?locale=uk
    """
    from grunt.core.i18n import translation_service

    translations = translation_service.get_all_translations(locale)
    return translations
