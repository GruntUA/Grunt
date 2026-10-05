from __future__ import annotations

from typing import Any

import grunt
from grunt.i18n import translation_service


@grunt.whitelist(allow_guest=True)
async def get_translations(locale: str) -> dict[str, Any]:
    """Return the translation bundle for a locale.

    Shape: ``{"version": <tag>, "messages": {source | "ctx|msg": translated}}``.
    The frontend caches ``version`` and skips re-merging when it is unchanged.

    Call via: /api/v1/method/grunt.api.v1.translations.get_translations?locale=uk
    """
    return {
        "version": translation_service.catalog_version(locale),
        "messages": translation_service.get_all_translations(locale),
    }
