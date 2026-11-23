"""DocType.force_private_attachments: files of such documents are always private."""

import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from grunt.errors import APIError, ApplicationError
from grunt.storage import backends
from tests.support import make_user

ANN = "ann@example.com"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(tmp_path))


@pytest.fixture
async def secret_note(ctx):
    from grunt.api.v1.meta import save_doctype

    await ctx.new_doc("User", {"email": ANN, "first_name": "Ann", "last_name": "Test"})
    await save_doctype(
        doctype_data={
            "name": "SecretNote",
            "label": "Secret Note",
            "module": "core",
            "force_private_attachments": True,
            "fields": [
                {"fieldname": "content", "label": "Content", "fieldtype": "RichText"},
                {"fieldname": "scan", "label": "Scan", "fieldtype": "Attach"},
            ],
            "permissions": [{"role": "All", "actions": ["read", "write", "create"]}],
            "__is_new": True,
        }
    )
    await ctx.db._session().commit()


def _file(name: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"data"), filename=name, headers=Headers({"content-type": "text/plain"})
    )


@pytest.mark.asyncio
async def test_upload_asking_for_public_is_stored_private(ctx, secret_note, storage):
    from grunt.storage.doctypes.File.file import upload

    up = await upload(
        _file("passport.txt"),
        attached_to_doctype="SecretNote",
        attached_to_id="N-1",
        is_public=True,
    )

    assert not await ctx.db.get_value("File", up["id"], "is_public")


@pytest.mark.asyncio
async def test_a_private_file_cant_be_made_public(ctx, secret_note, storage):
    import grunt
    from grunt.storage.doctypes.File.file import upload

    up = await upload(_file("passport.txt"), attached_to_doctype="SecretNote")

    with pytest.raises((ApplicationError, APIError), match="Secret Note"):
        await grunt.save_doc("File", up["id"], {"is_public": True})


@pytest.mark.asyncio
async def test_a_file_public_before_the_flag_is_left_alone(ctx, secret_note, storage):
    import grunt
    from grunt.storage import files

    old = await files.store(b"old", "old.txt", "text/plain", is_public=True)
    await ctx.db.set_value("File", old["name"], "attached_to_doctype", "SecretNote")

    await grunt.save_doc("File", old["name"], {"file_name": "renamed.txt"})

    assert await ctx.db.get_value("File", old["name"], "is_public")


@pytest.mark.asyncio
async def test_a_public_library_file_linked_from_the_document_goes_private(
    ctx, secret_note, storage, db_session, engine
):
    import grunt
    from grunt.storage.doctypes.File.file import upload

    async with grunt.context(db_session, engine, make_user(ANN, roles=["All"])):
        mine = await upload(_file("photo.txt"), is_public=True)
        doc = await grunt.new_doc("SecretNote", {"scan": mine["url"]})
        await db_session.commit()

    row = await ctx.db.get_values(
        "File", mine["id"], ["is_public", "attached_to_doctype", "attached_to_id"]
    )
    assert not row["is_public"]
    assert (row["attached_to_doctype"], row["attached_to_id"]) == ("SecretNote", doc["name"])


def test_doctype_cant_be_both_public_and_private():
    from pydantic import ValidationError

    from grunt.metadata.doctype import DocType

    with pytest.raises(ValidationError, match="both public and always private"):
        DocType(
            name="MixedNote",
            label="Mixed Note",
            module="core",
            public_attachments=True,
            force_private_attachments=True,
            fields=[{"fieldname": "content", "label": "Content", "fieldtype": "Data"}],
        )
