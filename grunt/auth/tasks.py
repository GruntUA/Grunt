"""Auth tasks - run by the task worker."""

from __future__ import annotations

import grunt
from grunt import log
from grunt.site.manager import site_manager
from grunt.tasks.broker import retryable_task


@retryable_task()
async def close_idle_sessions() -> None:
    """Mark sessions idle past ``SystemSettings.session_timeout`` inactive.

    Sign-in and the session listing close a user's own idle sessions too;
    this catches devices nobody signs in from again.
    """
    from grunt.auth.doctypes.UserSession.user_session import deactivate_expired
    from grunt.auth.service import session_ttl_minutes

    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session, grunt.system_context(session, eng):
        closed = await deactivate_expired(None, await session_ttl_minutes())
        await session.commit()
    if closed:
        log.info("auth.idle_sessions_closed", count=closed)
