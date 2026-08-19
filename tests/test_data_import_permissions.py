"""Regression: run_import_job() queued a background import task that runs
as SYSTEM_USER (bypassing every permission check) with NO check of its own
that the calling user is even allowed to work with DataImport at all —
DataImport itself is create/write/delete-restricted to "System Manager", but
nothing enforced that on the one action that actually executes the write.
download_template() had the same gap for the (much lower severity) template
metadata endpoint.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.support import make_user

GUARDED_IMPORT_TARGET = {
    "name": "ImportTargetSecret",
    "label": "Import Target Secret",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Text"},
    ],
    "permissions": [{"role": "DataOwner", "read": True, "write": True, "create": True}],
}


@pytest.fixture
async def guarded_import_target(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**GUARDED_IMPORT_TARGET, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_run_import_job_denies_non_system_manager(ctx, db_session, engine):
    from grunt.api.v1.data_import import run_import_job
    from grunt.app import grunt

    outsider = make_user("outsider@grunt.example.com")
    async with grunt.context(db_session, engine, outsider):
        with pytest.raises(HTTPException) as excinfo:
            await run_import_job("nonexistent-id")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_run_import_job_allows_system_manager(ctx, db_session, engine):
    from grunt.api.v1.data_import import run_import_job
    from grunt.app import grunt

    manager = make_user("dm@grunt.example.com", roles=["System Manager"])
    async with grunt.context(db_session, engine, manager):
        # The guard passes; the id doesn't exist so the queued task will
        # itself fail later, in the background — this call only proves the
        # permission check no longer blocks a legitimate System Manager.
        result = await run_import_job("nonexistent-id")
    assert result["name"] == "nonexistent-id"


@pytest.mark.asyncio
async def test_download_template_denies_user_without_read(
    ctx, guarded_import_target, db_session, engine
):
    from grunt.api.v1.data_import import download_template
    from grunt.app import grunt

    outsider = make_user("outsider2@grunt.example.com")
    async with grunt.context(db_session, engine, outsider):
        with pytest.raises(HTTPException) as excinfo:
            await download_template("ImportTargetSecret")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_download_template_allows_user_with_read(
    ctx, guarded_import_target, db_session, engine
):
    from grunt.api.v1.data_import import download_template
    from grunt.app import grunt

    owner = make_user("owner@grunt.example.com", roles=["DataOwner"])
    async with grunt.context(db_session, engine, owner):
        result = await download_template("ImportTargetSecret")
    assert result["filename"]
