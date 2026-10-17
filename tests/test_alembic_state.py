"""Alembic history of a site against the running code: stamp, up to date, and a
database migrated by a newer release (the code was rolled back past a migration)."""

from pathlib import Path

import pytest
import sqlalchemy as sa

from grunt.db.alembic_utils import DatabaseAheadError, migration_state, sync_site


def test_rolled_back_code_refuses_to_migrate(tmp_path: Path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'site.db'}"
    sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}").dispose()

    assert sync_site(db_url) == "stamped"
    state = migration_state(db_url)
    assert state.known and state.current == state.head
    assert sync_site(db_url) == "up to date"

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'site.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text("update alembic_version set version_num = '9999_future'"))
    engine.dispose()

    assert not migration_state(db_url).known
    with pytest.raises(DatabaseAheadError, match="9999_future"):
        sync_site(db_url)
