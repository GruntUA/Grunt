"""Public site configuration — the handful of SystemSettings values the SPA
needs before (and without) authentication: branding, locale, date/time
presentation, whether self-registration is open.

Call via: /api/v1/method/grunt.api.v1.site_config.get_public_config
"""

from __future__ import annotations

from typing import Any

import grunt


@grunt.whitelist(allow_guest=True)
async def get_public_config() -> dict[str, Any]:
    """Return the non-sensitive SystemSettings values consumed by the frontend.

    ``languages`` is the UI language switcher's list (``[{code, name}]``) —
    every locale with a translation catalog, named in its own language.
    """
    from grunt.i18n import translation_service
    from grunt.i18n.service import normalize_lang
    from grunt.site.settings import get_system_settings

    s = await get_system_settings()
    return {
        "app_name": s.get("app_name") or "Ґрунт",
        "app_logo": s.get("app_logo") or "",
        "language": normalize_lang(s.get("language")) or translation_service.default_lang(),
        "languages": [
            {"code": c, "name": translation_service.language_name(c)}
            for c in translation_service.ui_languages()
        ],
        "timezone": s.get("timezone") or "",
        "date_format": s.get("date_format") or "dd.mm.yyyy",
        "allow_user_registration": bool(s.get("allow_user_registration")),
    }
