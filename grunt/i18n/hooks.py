"""Doc-event hooks for the i18n module.

Wired from :mod:`grunt.core_hooks` — keeps the request-language negotiator's
accepted-language set in sync with the ``geo.Language`` table.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


async def refresh_supported_languages(**_kwargs: object) -> None:
    """Re-read active ``Language`` codes into the i18n negotiator.

    Doc-event target for ``Language`` after_save / after_delete. Runs inside the
    saving request, so a grunt context/session is already bound.
    """
    from grunt.app import grunt
    from grunt.i18n import translation_service

    try:
        rows = await grunt.db.get_all(
            "Language", filters={"is_active": True}, fields=["code"], limit=None
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("i18n.refresh_languages_skipped", error=str(e))
        return

    codes = {r["code"] for r in rows if r.get("code")}
    if codes:
        translation_service.set_supported(codes)
    translation_service.invalidate()
