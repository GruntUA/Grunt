"""Startup - fixture loading utilities for DocTypes and Workspaces."""

import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from grunt import log
from grunt.fixtures import apply_doctype_fixture
from grunt.standard_records import apply_records

_GRUNT_ROOT = Path(__file__).parent.parent  # grunt/startup/../ = grunt/


async def load_core_fixtures(session: AsyncSession, eng: AsyncEngine) -> None:
    """Load seed fixtures from grunt/*/fixtures/*.json (core module data).

    Scans all grunt/<module>/fixtures/ directories and applies records
    that don't yet exist in the database, then the core standard records
    (grunt/<module>/records/). Safe to call repeatedly.
    """
    for fixtures_dir in sorted(_GRUNT_ROOT.glob("*/fixtures")):
        for fx_file in sorted(fixtures_dir.glob("*.json")):
            try:
                fx = json.loads(fx_file.read_text())
                fx_doctype = fx.get("doctype", "")
                records = fx.get("records", [])
                if not fx_doctype or not records:
                    continue
                written = await apply_doctype_fixture(
                    fx_doctype, records, session, eng, sync=bool(fx.get("sync"))
                )
                if written:
                    log.info(
                        "startup.core_fixture_applied",
                        file=fx_file.name,
                        doctype=fx_doctype,
                        count=written,
                    )
            except Exception as e:
                log.warning("startup.core_fixture_failed", file=fx_file.name, error=str(e))

    count = await apply_records("grunt", session, eng)
    if count:
        log.info("startup.standard_records_applied", app="grunt", count=count)
