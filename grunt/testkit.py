"""Reusable pytest fixtures for testing apps built on grunt.

Grunt's own ``tests/conftest.py`` builds a single-test-engine environment
inline, scoped to ``grunt/*/doctypes/``. External apps (tsnap, hrm, car_ua,
...) need the exact same machinery, plus their own ``{module}/doctypes/``
directories loaded into the registry alongside grunt's core ones, and their
package directory on ``sys.path`` so intra-app imports (e.g.
``car_ua.services.x``) resolve. This module factors that out so each app's
conftest.py doesn't reimplement the SA_METADATA bootstrap/teardown dance.

Usage, in the app's ``tests/conftest.py``::

    from pathlib import Path
    from grunt.testkit import make_app_fixtures

    # Fixtures must live in module globals for pytest to discover them -
    # the factory returns them as a dict for exactly that purpose.
    globals().update(make_app_fixtures(Path(__file__).parent.parent, "tsnap"))
"""

import asyncio
import atexit
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import grunt
from grunt.apps.manifest import read_manifest
from grunt.apps.required import dependencies
from grunt.config import settings
from grunt.db.dialects import dialect_for
from grunt.db.session import get_engine as _get_engine_dep
from grunt.db.session import get_session
from grunt.document.registry import document_registry
from grunt.document.serde import to_json
from grunt.local import require_session, system_context
from grunt.main import app
from grunt.metadata.compiler import SA_METADATA, compile_doctype_to_table, get_compiled_metadata
from grunt.metadata.doctype import DocType
from grunt.metadata.extensions import app_extensions, apply_extensions
from grunt.metadata.registry import doctype_registry
from grunt.search.service import search_index_service
from grunt.site.manager import current_site, site_manager
from grunt.startup.doctypes import _find_doctype_dirs
lazy from grunt.apps.loader import load_app
lazy from grunt.auth.doctypes.UserSession.user_session import open_session
lazy from grunt.auth.session_cookie import SESSION_COOKIE
lazy from grunt.auth.users import create_user
lazy from grunt.document.api import documents

settings.rate_limit_enabled = False

logger = logging.getLogger(__name__)

# Fixed DocType-registry key for the whole test process - set explicitly via
# the same ContextVar production code uses, rather than relying on
# SiteManager.get_active_site()'s file-based fallback (see conftest.py's
# identical _TEST_SITE for the full rationale).
_TEST_SITE = "__pytest__"


def _toml(value: Any) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def write_app_manifest(app_dir: Path, project: dict[str, Any] | None = None, **tool: Any) -> None:
    """Write a minimal pyproject.toml that makes *app_dir* a Grunt app: ``project``
    goes to ``[project]``, keyword arguments to ``[tool.grunt]``."""
    lines = ["[project]", *(f"{k} = {_toml(v)}" for k, v in (project or {}).items())]
    lines += ["", "[tool.grunt]", *(f"{k} = {_toml(v)}" for k, v in tool.items())]
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "pyproject.toml").write_text("\n".join(lines) + "\n")


def _with_dependencies(app_dir: Path) -> list[Path]:
    """*app_dir* and the apps it ``depends_on`` (sibling dirs), dependencies first."""
    ordered: list[Path] = []

    def visit(path: Path) -> None:
        if path in ordered or not path.is_dir():
            return
        for dep in dependencies(path):
            visit(path.parent / dep.name)
        ordered.append(path)

    visit(app_dir)
    return ordered


def _app_doctype_dirs(app_dir: Path) -> list[Path]:
    modules = read_manifest(app_dir)["modules"]
    return [d for m in modules if (d := app_dir / m / "doctypes").is_dir()]


def bind_test_site(engine: AsyncEngine, session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Make the test site ``__pytest__`` use the test engine and a throwaway folder.

    Code that opens its own session outside a request (server scripts, the
    error log, background tasks) goes through ``site_manager``; left alone it
    would open ``sites/__pytest__/grunt.db`` - a real file on a dev machine,
    a missing one in CI. The sites folder is a temporary one owned by the test
    process (the bench's own may be absent or not writable - a bare checkout),
    removed at exit; the site folder in it exists for storage checks.
    """
    sites_dir = Path(tempfile.mkdtemp(prefix="grunt-test-sites-"))
    atexit.register(shutil.rmtree, sites_dir, ignore_errors=True)
    site_manager.sites_dir = sites_dir
    (sites_dir / _TEST_SITE).mkdir()
    site_manager.engines[_TEST_SITE] = engine
    site_manager.session_makers[_TEST_SITE] = session_maker


# DDL statements and the table each one touches; any other DDL is "unknown".
_DDL_TABLE = re.compile(
    r"^\s*(?:"
    r"(?:CREATE|ALTER|DROP)\s+(?:VIRTUAL\s+|TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
    r"|CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+(?:ONLY\s+)?"
    r')[`"]?(\w+)[`"]?(?=[\s(;]|$)',
    re.IGNORECASE,
)
_DDL = ("CREATE", "ALTER", "DROP")
# A statement that writes rows - the table it writes is emptied before the
# next test. One whose table can't be told (a CTE, COPY, ...) empties them all.
_DML = ("INSERT", "UPDATE", "DELETE", "REPLACE", "WITH", "MERGE", "COPY", "TRUNCATE")
_DML_TABLE = re.compile(
    r"^\s*(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?"
    r"|DELETE\s+FROM)\s+(?:ONLY\s+)?(?:[`\"]?\w+[`\"]?\.)?[`\"]?(\w+)[`\"]?(?=[\s(;]|$)",
    re.IGNORECASE,
)
# Comments in front of a statement: "-- ...", "/* ... */".
_LEADING_COMMENTS = re.compile(r"^(?:\s*(?:--[^\n]*(?:\n|$)|/\*.*?\*/))+", re.DOTALL)
# Execution option marking TestSchema's own connections: what they run is the
# cleanup itself, not a test's writes - anything else, a test's background task
# writing during the cleanup included, stays watched.
_OWN = "grunt_testkit_own"


class TestSchema:
    """The test database's schema - made once, emptied between tests.

    Creating and dropping every DocType table around each test cost more than
    most tests themselves (~200 ms on SQLite, ~280 ms on PostgreSQL); emptying
    them takes a fraction of that - and emptying only the tables written since
    the last test a fraction again (a ``TRUNCATE`` of every table cost
    PostgreSQL ~0.2 s a test, a quarter of the suite). The SQL a test runs is
    watched:

    * tables it wrote rows to are emptied before the next test - a write whose
      table can't be told empties them all;

    * tables it created (its own DocTypes) are dropped after it - the rest of
      the schema stays;
    * if it changed a table of the schema (ALTER, an index, DROP, a recompiled
      Table in the MetaData) or ran DDL whose table can't be told, the whole
      schema is dropped and the next test gets a fresh one, as before.
    """

    __test__ = False  # not a test class, despite the name

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._tables: dict[str, int] | None = None  # name -> id(Table) as created
        self._db_tables: set[str] = set()  # what the database holds then (search index too)
        self._touched: set[str] = set()
        self._unknown_ddl = False
        # Tables rows were written to since the tables were emptied - lowercase:
        # unquoted names fold (PostgreSQL) or compare case-blind (SQLite).
        self._written: set[str] = set()
        self._unknown_write = False
        event.listen(engine.sync_engine, "before_cursor_execute", self._watch)

    def _watch(self, conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        if conn.get_execution_options().get(_OWN):
            return
        statement = _LEADING_COMMENTS.sub("", statement).lstrip()
        head = statement[:8].upper()
        if head.startswith(_DML):
            if m := _DML_TABLE.match(statement):
                self._written.add(m.group(1).lower())
            else:
                self._unknown_write = True
        elif head.startswith(_DDL):
            if m := _DDL_TABLE.match(statement):
                self._touched.add(m.group(1).lower())
            else:
                self._unknown_ddl = True

    def _own(self, conn: Any) -> Any:
        """*conn* (an async connection) marked as the cleanup's own - not watched."""
        return conn.execution_options(**{_OWN: True})

    @staticmethod
    def _snapshot() -> dict[str, int]:
        return {
            name: id(table)
            for metadata in (SA_METADATA, get_compiled_metadata())
            for name, table in metadata.tables.items()
        }

    async def prepare(self) -> None:
        """Before a test, once its DocTypes are compiled: make the schema if there
        is none, else empty the tables written since the last test."""
        # Taken now: what a test's leftover task writes during the cleanup
        # stays noted for the next one.
        written, unknown_write = self._written, self._unknown_write
        self._written, self._unknown_write = set(), False
        try:
            if self._tables is None:
                async with self.engine.begin() as conn:
                    conn = await self._own(conn)
                    await conn.run_sync(SA_METADATA.create_all)
                    await conn.run_sync(get_compiled_metadata().create_all)
                await search_index_service.ensure_table(self.engine)
                async with self.engine.connect() as conn:
                    conn = await self._own(conn)
                    self._db_tables = set(
                        await conn.run_sync(lambda c: inspect(c).get_table_names())
                    )
                self._tables = self._snapshot()
            else:
                names = (
                    list(self._tables)
                    if unknown_write
                    else [name for name in self._tables if name.lower() in written]
                )
                async with self.engine.begin() as conn:
                    conn = await self._own(conn)
                    await dialect_for(conn).empty_tables(conn, names)
                    await search_index_service.empty(conn)
        except BaseException:
            # Not emptied - the next attempt still has to.
            self._written |= written
            self._unknown_write |= unknown_write
            raise
        # The schema's own DDL (search index tables, made on their own
        # connections) isn't a test's.
        self._touched.clear()
        self._unknown_ddl = False

    async def finish(self) -> None:
        """After a test: drop the tables it created; drop the whole schema if it
        changed the schema's own."""
        metadata = get_compiled_metadata()
        current = self._snapshot()
        base = self._tables
        changed = (
            base is None
            or self._unknown_ddl
            or bool(self._touched & {n.lower() for n in (*base.keys(), *self._db_tables)})
            or any(current.get(name) != table_id for name, table_id in base.items())
        )
        if changed:
            async with self.engine.begin() as conn:
                conn = await self._own(conn)
                await conn.run_sync(metadata.drop_all)
                await conn.run_sync(SA_METADATA.drop_all)
            await search_index_service.drop_table(self.engine)
            self._tables = None
        elif self._touched:
            async with self.engine.begin() as conn:
                conn = await self._own(conn)
                quote = conn.dialect.identifier_preparer.quote
                for name in self._touched:
                    await conn.execute(text(f"DROP TABLE IF EXISTS {quote(name)}"))
        # The test's own tables leave the MetaData too (with or without DDL).
        keep = set() if changed or base is None else base.keys()
        for name in [t for t in metadata.tables if t.startswith("grunt_") and t not in keep]:
            metadata.remove(metadata.tables[name])


def isolate_from_redis() -> None:
    """Keep tests off Redis - the caches, the rate limiter and the cache bus.

    Keys are built from the site name, and every test process (each xdist
    worker) runs the same site ``__pytest__``: through one Redis they would
    read each other's cached documents (a user's roles from another worker's
    test) - and the dev server's Redis on a dev machine. CI has no Redis;
    without it here too, local runs behave like CI. ``REDIS_URL`` comes from
    ``.env`` and the task broker is already built by the time a conftest runs:
    its sends are held by :func:`hold_task_queue`; everything else checks the
    setting when it is used.
    """
    settings.redis_url = None


#: Background tasks sent (``.kiq()``) during the test run - see :func:`hold_task_queue`.
sent_tasks: list[Any] = []


def hold_task_queue() -> None:
    """Keep ``.kiq()`` from dispatching anything while tests run.

    Without it a task goes to the real Redis of a dev machine (a running dev
    worker may pick it up) or, with no ``REDIS_URL`` as in CI, runs in-process
    right away - concurrently with the test that queued it and with the next
    test's table drop (an e-mail queue run reclaiming a row the test is
    checking, "no such table"). Sent messages land in :data:`sent_tasks`;
    a test that needs a task to run calls it directly or patches its ``kiq``.
    """
    from grunt.tasks.broker import broker

    async def _hold(message: Any) -> None:
        sent_tasks.append(message)

    broker.kick = _hold  # type: ignore[method-assign]


def worker_database_url() -> str:
    """``TEST_DATABASE_URL`` (in-memory SQLite by default) for this test process.

    On a server backend each test process gets its own database, made afresh
    for the run (``grunt_test`` → ``grunt_test_gw0`` under pytest-xdist,
    ``grunt_test_main`` without it): the fixtures create and drop every table
    around each test, so workers sharing one database break each other's
    tables ("relation does not exist", deadlocks), and whatever an interrupted
    run left behind must not reach the next one - as in CI, where the database
    is always new. The URL's own database only serves to connect.
    """
    url = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")
    dialect = dialect_for(url)
    if dialect.file_based:
        return url
    parsed = make_url(url)
    name = f"{parsed.database}_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"
    asyncio.run(dialect.create_database(parsed, name, replace=True))
    return parsed.set(database=name).render_as_string(hide_password=False)


def make_app_fixtures(app_dir: Path, app_name: str) -> dict[str, Any]:
    """Build the standard (setup_db, db_session, engine, ctx, client) fixture set
    for an external app's test suite.

    Set ``TEST_DATABASE_URL`` to point ``test_engine`` at Postgres/MySQL instead
    of the in-memory sqlite default - same convention as grunt's own conftest.
    """
    # Must happen at conftest-import time, not inside a fixture: pytest imports
    # every test module during collection, before any fixture runs, so a test
    # file's module-level `from car_ua.services... import ...` needs this on
    # sys.path already.
    # The app's dependencies come along: their doctypes, controllers and modules.
    app_dirs = _with_dependencies(app_dir)
    for path in app_dirs:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    test_url = worker_database_url()
    test_engine = create_async_engine(
        test_url,
        echo=False,
        json_serializer=to_json,
        connect_args=dialect_for(test_url).connect_args(test_url),
    )
    dialect_for(test_engine).attach_functions(test_engine)  # same Unicode lower() as sites
    TestSessionLocal = async_sessionmaker(  # noqa: N806 - sessionmaker factory, PascalCase by convention
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    bind_test_site(test_engine, TestSessionLocal)
    test_schema = TestSchema(test_engine)
    hold_task_queue()
    isolate_from_redis()

    async def override_get_session():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session

    async def override_get_engine():
        return test_engine

    app.dependency_overrides[_get_engine_dep] = override_get_engine

    dependencies_loaded = False

    async def load_dependencies() -> None:
        """Load the apps this one depends on the way production does (hooks,
        pages, assets) - their website hooks shape this app's pages too."""
        nonlocal dependencies_loaded
        if dependencies_loaded:
            return

        for path in app_dirs[:-1]:
            await load_app(app, path)
        dependencies_loaded = True

    @pytest_asyncio.fixture
    async def setup_db():
        """Create tables before each test, drop after. Clear registry.

        Loads grunt's core doctypes plus this app's own. Not autouse (unlike
        grunt core's own conftest): app test directories mix DB-backed tests
        with plain sync unit tests, and pytest-asyncio hard-errors when a sync
        test is forced to depend on an async autouse fixture. Pulled in
        transitively by db_session/engine/ctx/client below - request one of
        those (or setup_db itself) in tests that need the database.
        """
        site_token = current_site.set(_TEST_SITE)
        try:
            doctype_registry.reset()

            dt_dirs = [*_find_doctype_dirs(), *(d for a in app_dirs for d in _app_doctype_dirs(a))]
            dt_files = sorted(f for d in dt_dirs for f in d.glob("**/*.json"))
            # Fields the apps add to each other's (and core) DocTypes, as `migrate` merges them.
            extensions: dict[str, list] = {}
            for path in app_dirs:
                for ext in app_extensions(path, path.name):
                    extensions.setdefault(ext.doctype, []).append(ext)
            for dt_file in dt_files:
                try:
                    dt_data = json.loads(dt_file.read_text())
                    dt_obj = DocType.model_validate(dt_data)
                    if not dt_obj.app:
                        owner = next((a for a in app_dirs if dt_file.is_relative_to(a)), None)
                        dt_obj.app = owner.name if owner else "grunt"
                    dt_obj = apply_extensions(dt_obj, extensions.get(dt_obj.name))
                    compile_doctype_to_table(dt_obj)
                    doctype_registry._doctypes[dt_obj.name] = dt_obj
                except Exception as exc:
                    logger.warning("Failed to load or compile doctype from %s: %s", dt_file, exc)

            for path in app_dirs:
                document_registry.index_external_app_controllers(path)
            await load_dependencies()

            await test_schema.prepare()  # made once, then just emptied

            yield

            await test_schema.finish()  # drops it only if this test changed it
        finally:
            current_site.reset(site_token)

    @pytest_asyncio.fixture
    async def db_session(setup_db):
        async with TestSessionLocal() as session:
            yield session

    @pytest.fixture
    def engine(setup_db) -> AsyncEngine:
        return test_engine

    @pytest_asyncio.fixture
    async def client():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest_asyncio.fixture
    async def ctx(db_session: AsyncSession, engine: AsyncEngine):
        """Provide an active grunt context with SYSTEM_USER for tests."""
        async with system_context(db_session, engine):
            yield grunt

    return {
        "setup_db": setup_db,
        "db_session": db_session,
        "engine": engine,
        "client": client,
        "ctx": ctx,
    }


async def signed_in_cookie(email: str, roles: tuple[str, ...] = ()) -> str:
    """A browser signed in as a new user with exactly *roles*: the ``Cookie``
    header it sends - for site pages that know their reader (a preview).
    Needs an active grunt context (the ``ctx`` fixture)."""

    user = await create_user(email, "Str0ngPass", "Test", "Reader", None)
    assert user.id is not None
    # Explicitly: the first user of a database becomes a System Manager.
    await documents.save_doc("User", user.id, {"roles": [{"role_name": r} for r in roles]})
    _sid, token = await open_session(user.id, None, None)
    await require_session().commit()
    return f"{SESSION_COOKIE}={token}"
