"""Controller for the SystemSettings singleton.

It drops the in-process settings cache whenever an admin saves the form, so the
new values take effect immediately in this worker (other workers pick them up
via the cache TTL - see ``grunt/site/settings.py``), and re-applies the default
language to the i18n service.
"""

from __future__ import annotations

from grunt.document.base import Document
from grunt.i18n import translation_service
from grunt.site.settings import clear_settings_cache


class SystemSettings(Document):
    async def after_save(self) -> None:
        clear_settings_cache()

        translation_service.set_default(self.get("language"))
