"""Controller for the SystemSettings singleton.

Its only job is to drop the in-process settings cache whenever an admin saves
the form, so the new values take effect immediately in this worker (other
workers pick them up via the cache TTL — see ``grunt/site/settings.py``).
"""

from __future__ import annotations

from grunt.document.base import Document


class SystemSettings(Document):
    async def after_save(self) -> None:
        from grunt.site.settings import clear_settings_cache

        clear_settings_cache()
