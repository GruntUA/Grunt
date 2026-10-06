"""Personal file spaces: a home folder per user, folders and files inside it
private to the owner, sharing a folder shares its subtree, quotas."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from grunt.errors import ApplicationError
from grunt.storage import backends
from tests.support import make_user

ANN = "ann@example.com"
BOB = "bob@example.com"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(backends, "_resolve_local_upload_dir", lambda site: str(tmp_path))


@pytest.fixture
async def people(ctx):
    for email, first in ((ANN, "Ann"), (BOB, "Bob")):
        await ctx.new_doc("User", {"email": email, "first_name": first, "last_name": "Test"})
    await ctx.db._session().commit()


def _as(email: str, *roles: str):
    return make_user(email, roles=list(roles))


def _file(name: str, content: bytes = b"data") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content), filename=name, headers=Headers({"content-type": "text/plain"})
    )


async def _ann_space(db_session, engine) -> tuple[str, str, str]:
    """Ann's home, a ``Work/Drafts`` subtree and a file in Drafts."""
    import grunt
    from grunt.storage.doctypes.File.file import upload
    from grunt.storage.doctypes.FileFolder.file_folder import get_home_folder

    async with grunt.context(db_session, engine, _as(ANN)):
        home = (await get_home_folder())["name"]
        work = (await grunt.new_doc("FileFolder", {"folder_name": "Work", "parent_folder": home}))[
            "name"
        ]
        drafts = (
            await grunt.new_doc("FileFolder", {"folder_name": "Drafts", "parent_folder": work})
        )["name"]
        await upload(_file("plan.txt"), folder=drafts)
        await db_session.commit()
    return home, work, drafts


async def _share(ctx, folder: str, permission: str) -> None:
    await ctx.new_doc(
        "SharedWith",
        {
            "reference_doctype": "FileFolder",
            "reference_id": folder,
            "user": BOB,
            "permission": permission,
        },
    )
    await ctx.db._session().commit()


@pytest.mark.asyncio
async def test_home_folder_is_created_once_and_named_after_the_user(
    ctx, people, db_session, engine
):
    import grunt
    from grunt.storage.doctypes.FileFolder.file_folder import get_home_folder

    async with grunt.context(db_session, engine, _as(ANN)):
        first = await get_home_folder()
        again = await get_home_folder()
    assert first["name"] == again["name"]
    assert first["folder_name"] == "Test Ann"
    row = await ctx.db.get_value("FileFolder", first["name"], "*")
    assert row["space_user"] == ANN and row["is_home"]


@pytest.mark.asyncio
async def test_subfolders_and_files_take_the_space_of_their_parent(
    ctx, people, storage, db_session, engine
):
    _, work, drafts = await _ann_space(db_session, engine)
    assert await ctx.db.get_value("FileFolder", drafts, "space_user") == ANN
    [f] = await ctx.db.get_all("File", filters={"folder": drafts}, fields=["is_public"])
    assert not f["is_public"]


@pytest.mark.asyncio
async def test_a_folder_needs_a_parent(ctx, people, db_session, engine):
    import grunt

    async with grunt.context(db_session, engine, _as(ANN)):
        with pytest.raises(HTTPException) as exc:
            await grunt.new_doc("FileFolder", {"folder_name": "Loose"})
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_another_users_space_is_invisible(ctx, people, storage, db_session, engine):
    import grunt
    from grunt.document.base import Document
    from grunt.storage.doctypes.File.file import upload

    home, work, drafts = await _ann_space(db_session, engine)
    async with grunt.context(db_session, engine, _as(BOB)):
        assert await grunt.get_list("File") == []
        assert all(r["space_user"] == BOB for r in await grunt.get_list("FileFolder"))
        roots = await Document.get_tree_children("FileFolder")
        assert home not in {n["name"] for n in roots}
        with pytest.raises(HTTPException) as read:
            await grunt.get_doc("FileFolder", work)
        assert read.value.status_code == 403
        with pytest.raises(HTTPException):
            await grunt.new_doc("FileFolder", {"folder_name": "Intruder", "parent_folder": work})
        with pytest.raises(ApplicationError):
            await upload(_file("spam.txt"), folder=drafts)
        with pytest.raises(HTTPException):
            await Document.move_tree_node("FileFolder", drafts, new_parent_id=home)


@pytest.mark.asyncio
async def test_read_share_opens_the_whole_subtree(ctx, people, storage, db_session, engine):
    import grunt
    from grunt.document.base import Document
    from grunt.storage.doctypes.File.file import upload

    home, work, drafts = await _ann_space(db_session, engine)
    await _share(ctx, work, "Read")
    async with grunt.context(db_session, engine, _as(BOB)):
        assert [f["file_name"] for f in await grunt.get_list("File")] == ["plan.txt"]
        assert (await grunt.get_doc("FileFolder", drafts))["folder_name"] == "Drafts"
        # The shared folder surfaces as a root - its parent (Ann's home) stays hidden.
        roots = {n["name"] for n in await Document.get_tree_children("FileFolder")}
        assert work in roots and home not in roots
        with pytest.raises(ApplicationError):
            await upload(_file("note.txt"), folder=drafts)


@pytest.mark.asyncio
async def test_write_share_lets_colleague_file_into_the_owners_space(
    ctx, people, storage, db_session, engine
):
    import grunt
    from grunt.storage.doctypes.File.file import upload

    _, work, drafts = await _ann_space(db_session, engine)
    await _share(ctx, work, "Write")
    async with grunt.context(db_session, engine, _as(BOB)):
        up = await upload(_file("note.txt"), folder=drafts)
        sub = await grunt.new_doc("FileFolder", {"folder_name": "Bob's", "parent_folder": drafts})
    assert sub["space_user"] == ANN
    # The space owner manages everything in it - also what Bob put there.
    async with grunt.context(db_session, engine, _as(ANN)):
        await grunt.delete_doc("File", up["id"])


@pytest.mark.asyncio
async def test_system_manager_sees_every_space(ctx, people, storage, db_session, engine):
    import grunt

    await _ann_space(db_session, engine)
    async with grunt.context(db_session, engine, _as("boss@example.com", "System Manager")):
        assert [f["file_name"] for f in await grunt.get_list("File")] == ["plan.txt"]


@pytest.mark.asyncio
async def test_moving_a_folder_to_another_space_carries_its_subtree(
    ctx, people, storage, db_session, engine
):
    import grunt
    from grunt.document.base import Document
    from grunt.storage.doctypes.FileFolder.file_folder import get_home_folder

    _, work, drafts = await _ann_space(db_session, engine)
    async with grunt.context(db_session, engine, _as(BOB)):
        bob_home = (await get_home_folder())["name"]
        await db_session.commit()
    async with grunt.context(db_session, engine, _as("boss@example.com", "System Manager")):
        await Document.move_tree_node("FileFolder", work, new_parent_id=bob_home)
    for folder in (work, drafts):
        assert await ctx.db.get_value("FileFolder", folder, "space_user") == BOB


@pytest.mark.asyncio
async def test_quota_blocks_uploads_beyond_the_limit(ctx, people, storage, db_session, engine):
    import grunt
    from grunt.site.settings import clear_settings_cache
    from grunt.storage.doctypes.File.file import upload
    from grunt.storage.doctypes.FileFolder.file_folder import get_home_folder, get_storage_usage

    await ctx.set_value("User", ANN, "storage_quota_mb", 1)
    await ctx.db._session().commit()
    clear_settings_cache()
    async with grunt.context(db_session, engine, _as(ANN)):
        home = (await get_home_folder())["name"]
        await upload(_file("small.bin", b"x" * 700_000), folder=home)
        with pytest.raises(HTTPException) as exc:
            await upload(_file("big.bin", b"y" * 500_000), folder=home)
        assert exc.value.status_code == 422
        usage = await get_storage_usage()
        with pytest.raises(ApplicationError):
            await get_storage_usage(BOB)
    assert usage == {"used": 700_000, "quota": 1024 * 1024}


@pytest.mark.asyncio
async def test_assign_spaces_moves_library_into_authors_homes(ctx, people, db_session, engine):
    import grunt
    from grunt.storage.spaces import assign_spaces

    folders = (await grunt.get_meta("FileFolder")).table
    files = (await grunt.get_meta("File")).table
    session = ctx.db._session()
    await session.execute(
        folders.insert().values(name="lib1", folder_name="Old library", owner=ANN)
    )
    await session.execute(
        folders.insert().values(name="lib2", folder_name="Inside", parent_folder="lib1", owner=BOB)
    )
    await session.execute(
        files.insert().values(
            name="f1",
            file_name="loose.txt",
            content_hash="a" * 64,
            file_url="/x",
            uploaded_by=BOB,
            owner=BOB,
            is_public=True,
        )
    )
    await session.commit()

    dry = await assign_spaces(apply=False)
    assert dry["folders"] == [{"folder": "Old library", "owner": ANN}]
    assert await ctx.db.get_value("FileFolder", "lib1", "space_user") is None

    await assign_spaces(apply=True)
    ann_home = await ctx.db.get_value("FileFolder", {"space_user": ANN, "is_home": 1})
    bob_home = await ctx.db.get_value("FileFolder", {"space_user": BOB, "is_home": 1})
    assert await ctx.db.get_value("FileFolder", "lib1", "parent_folder") == ann_home
    assert await ctx.db.get_value("FileFolder", "lib2", "space_user") == ANN
    moved = await ctx.db.get_value("File", "f1", ["folder", "is_public"], as_dict=True)
    assert moved["folder"] == bob_home and not moved["is_public"]


@pytest.mark.asyncio
async def test_own_home_comes_first_as_my_files(ctx, people, storage, db_session, engine):
    import grunt
    from grunt.document.base import Document
    from grunt.storage.doctypes.FileFolder.file_folder import get_home_folder

    ann_home, _, _ = await _ann_space(db_session, engine)
    boss = _as("boss@example.com", "System Manager")
    async with grunt.context(db_session, engine, boss):
        own = (await get_home_folder())["name"]
        await db_session.commit()
        roots = await Document.get_tree_children("FileFolder")
    assert [n["name"] for n in roots][:2] == [own, ann_home]
    assert roots[0]["display_title"] == "Мої файли"
    assert "display_title" not in roots[1]


@pytest.mark.asyncio
async def test_colleagues_directory_is_open_to_everyone_without_roles(
    ctx, people, db_session, engine
):
    import grunt
    from grunt.auth.doctypes.User.user import list_colleagues_api

    async with grunt.context(db_session, engine, _as(ANN)):
        people_list = await list_colleagues_api()
    emails = {p["email"] for p in people_list}
    assert {ANN, BOB} <= emails
    assert all(set(p) <= {"name", "email", "full_name", "avatar"} for p in people_list)
