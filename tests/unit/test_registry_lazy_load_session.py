"""Regression: DocTypeRegistry._lazy_load() used to always build its own
session via site_manager.get_active_site() / get_session_maker(), ignoring
any session already bound to the active grunt context. On a machine where
more than one site's database is reachable from the same process (e.g. a dev
box that also runs the test suite against a real, unrelated site), this
silently read from the *other* database instead of the one actually active
for the current call — found via a real live-site permission drift that this
leak masked for a long time (see ADR 006).

_lazy_load() must now prefer the ambient session (whatever grunt.context()
currently has bound) and only fall back to site_manager when nothing is
bound at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_lazy_load_uses_ambient_session_not_site_manager(
    ctx, db_session, engine, monkeypatch
):
    from grunt.metadata.doctype import DocType
    from grunt.metadata.registry import doctype_registry
    from grunt.site.manager import site_manager

    # register() both inserts the GruntMetaDoctype row and loads it into
    # memory — _lazy_load needs a real DB row to find, which testkit's
    # bulk JSON loader (in-memory dict assignment only) doesn't create.
    dt_in = DocType(name="LazyLoadTarget", label="Lazy Load Target", module="test", fields=[])
    await doctype_registry.register(dt_in, db_session, engine)
    await db_session.commit()

    def _fail_if_called(*args, **kwargs):
        raise AssertionError(
            "site_manager.get_active_site() must not be called when a "
            "grunt context session is already active"
        )

    monkeypatch.setattr(site_manager, "get_active_site", _fail_if_called)

    dt = await doctype_registry._lazy_load("LazyLoadTarget")
    assert dt is not None
    assert dt.name == "LazyLoadTarget"


@pytest.mark.asyncio
async def test_lazy_load_falls_back_to_site_manager_without_context():
    """No grunt.context() active at all — background-task shape. Must still
    go through site_manager rather than crash, and fail closed (None) when
    site_manager itself has nothing to resolve."""
    from grunt.metadata.registry import doctype_registry

    dt = await doctype_registry._lazy_load("DoesNotExistAnywhere")
    assert dt is None
