"""Nightly database upkeep - :meth:`Dialect.routine_maintenance` of the site.

SQLite: fresh planner statistics (``PRAGMA optimize``) and the pages freed by
deletions back to the file system (``PRAGMA incremental_vacuum``). PostgreSQL
does both by itself (autovacuum), so nothing runs there.
"""

from grunt import log
from grunt.db.dialects import dialect_for
from grunt.site.manager import site_manager
from grunt.tasks.broker import task


@task
async def run_maintenance() -> None:
    """Run the active site's routine database maintenance - see the module doc."""
    eng = site_manager.get_engine(site_manager.get_active_site())
    ran = await dialect_for(eng).routine_maintenance(eng)
    if ran:
        log.info("db.maintenance_done", statements=ran)
