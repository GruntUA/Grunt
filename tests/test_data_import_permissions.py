"""Regression: run_import_job() queued a background import task that runs
as SYSTEM_USER (bypassing every permission check) with NO check of its own
that the calling user is even allowed to work with DataImport at all —
DataImport itself is create/write/delete-restricted to "System Manager", but
nothing enforced that on the one action that actually executes the write.
download_template() had the same gap for the (much lower severity) template
metadata endpoint.

Both now also need the ``import`` permission on the target DocType - the
import writes into it as SYSTEM_USER.
"""

import pytest
from fastapi import HTTPException

from tests.support import make_user

GUARDED_IMPORT_TARGET = {
    "name": "ImportTargetSecret",
    "label": "Import Target Secret",
    "module": "core",
    "fields": [
        {"fieldname": "title", "label": "Title", "fieldtype": "Data"},
    ],
    "permissions": [
        {"role": "DataOwner", "actions": ["read", "write", "create", "import"]},
        {"role": "DataReader", "actions": ["read"]},
    ],
}


@pytest.fixture
async def guarded_import_target(ctx):
    from grunt.api.v1.meta import save_doctype

    await save_doctype(doctype_data={**GUARDED_IMPORT_TARGET, "__is_new": True})
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_run_import_job_denies_non_system_manager(ctx, db_session, engine):
    import grunt
    from grunt.api.v1.data_import import run_import_job

    outsider = make_user("outsider@grunt.example.com")
    async with grunt.context(db_session, engine, outsider):
        with pytest.raises(HTTPException) as excinfo:
            await run_import_job("nonexistent-id")
    assert excinfo.value.status_code == 403


async def _pending_import(db_session, engine) -> str:
    """A DataImport into the target, set up by someone allowed to."""
    import grunt
    from grunt.document.api import documents

    setter = make_user("setup@grunt.example.com", roles=["System Manager", "DataOwner"])
    async with grunt.context(db_session, engine, setter):
        doc = await documents.new_doc(
            "DataImport",
            {
                "doctype_name": "ImportTargetSecret",
                "file": "/files/rows.csv",
                "import_type": "Insert New",
            },
        )
    return doc["name"]


@pytest.mark.asyncio
async def test_run_import_job_needs_import_on_the_target(
    ctx, guarded_import_target, db_session, engine
):
    """System Manager may run DataImport, but not into a DocType they have no
    ``import`` on - the task would write there as SYSTEM_USER."""
    import grunt
    from grunt.api.v1.data_import import run_import_job

    name = await _pending_import(db_session, engine)

    manager = make_user("dm@grunt.example.com", roles=["System Manager"])
    async with grunt.context(db_session, engine, manager):
        with pytest.raises(HTTPException) as excinfo:
            await run_import_job(name)
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_run_import_job_allows_system_manager_with_import(
    ctx, guarded_import_target, db_session, engine
):
    import grunt
    from grunt.api.v1.data_import import run_import_job

    name = await _pending_import(db_session, engine)

    importer = make_user("di@grunt.example.com", roles=["System Manager", "DataOwner"])
    async with grunt.context(db_session, engine, importer):
        result = await run_import_job(name)
    assert result["name"] == name


@pytest.mark.asyncio
async def test_data_import_needs_import_on_the_target_when_saved(
    ctx, guarded_import_target, db_session, engine
):
    import grunt
    from grunt.document.api import documents

    manager = make_user("dm2@grunt.example.com", roles=["System Manager"])
    async with grunt.context(db_session, engine, manager):
        with pytest.raises(HTTPException) as excinfo:
            await documents.new_doc(
                "DataImport",
                {
                    "doctype_name": "ImportTargetSecret",
                    "file": "/files/rows.csv",
                    "import_type": "Insert New",
                },
            )
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_download_template_denies_user_without_read(
    ctx, guarded_import_target, db_session, engine
):
    import grunt
    from grunt.api.v1.data_import import download_template

    outsider = make_user("outsider2@grunt.example.com")
    async with grunt.context(db_session, engine, outsider):
        with pytest.raises(HTTPException) as excinfo:
            await download_template("ImportTargetSecret")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_download_template_denies_user_with_only_read(
    ctx, guarded_import_target, db_session, engine
):
    import grunt
    from grunt.api.v1.data_import import download_template

    reader = make_user("reader@grunt.example.com", roles=["DataReader"])
    async with grunt.context(db_session, engine, reader):
        with pytest.raises(HTTPException) as excinfo:
            await download_template("ImportTargetSecret")
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_download_template_allows_user_with_import(
    ctx, guarded_import_target, db_session, engine
):
    import grunt
    from grunt.api.v1.data_import import download_template

    owner = make_user("owner@grunt.example.com", roles=["DataOwner"])
    async with grunt.context(db_session, engine, owner):
        result = await download_template("ImportTargetSecret")
    assert result["filename"]
