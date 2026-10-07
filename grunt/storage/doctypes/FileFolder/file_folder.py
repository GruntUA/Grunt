from __future__ import annotations

from typing import Any

import grunt
from grunt import _
from grunt.api.context import whitelist
from grunt.document.base import Document
from grunt.i18n import pgettext
from grunt.permissions.roles import user_has_roles
from grunt.permissions.user_permissions import expand_tree_values
from grunt.storage import quota


class FileFolder(Document):
    """DocType controller for FileFolder - a node of a personal file space.

    A user's home folder (``is_home``) is the root of their space; every other
    folder sits inside one and takes its ``space_user`` from the parent, so the
    space - who owns it, whose quota it fills - is one column, not a tree walk.
    """

    folder_name: str
    parent_folder: str | None
    space_user: str | None
    is_home: bool

    _prev: dict[str, Any] | None = None

    async def before_save(self) -> None:
        if self.id and self._prev is None:
            self._prev = await grunt.db.get_value(
                "FileFolder", self.id, ["parent_folder", "space_user", "is_home"], as_dict=True
            )
        prev = self._prev or {}
        if prev.get("is_home"):
            self.is_home = True  # a home stays a home
        if self.is_home:
            await self._check_home(prev)
            return
        if not self.parent_folder:
            grunt.throw(_("A folder must be inside another folder"))
        if prev and prev.get("parent_folder") == self.parent_folder:
            self.space_user = prev.get("space_user")
            return
        parent = await grunt.db.get_value("FileFolder", self.parent_folder, "*")
        if parent is None:
            grunt.throw(_("Folder “%(folder)s” not found") % {"folder": self.parent_folder})
        await require_folder_write(parent)
        if prev.get("space_user") and prev["space_user"] != parent["space_user"]:
            await quota.ensure_room(parent["space_user"], await _subtree_size(str(self.id)))
        self.space_user = parent["space_user"]

    async def _check_home(self, prev: dict[str, Any]) -> None:
        if prev:
            if self.parent_folder:
                grunt.throw(_("A home folder can't be moved"))
            self.space_user = prev.get("space_user")
            return
        self.parent_folder = None
        user = grunt.get_user()
        if not self.space_user:
            self.space_user = user.email
        if self.space_user != user.email and not user_has_roles(user, ["System Manager"]):
            grunt.throw(_("You can only create your own home folder"), "PERMISSION_DENIED")
        if await grunt.db.exists("FileFolder", {"space_user": self.space_user, "is_home": 1}):
            grunt.throw(_("This user already has a home folder"))

    async def after_save(self) -> None:
        # A folder moved into another space carries its whole subtree along.
        prev = self._prev or {}
        if prev.get("space_user") and prev["space_user"] != self.space_user:
            subtree = await expand_tree_values("FileFolder", {str(self.id)})
            subtree.discard(str(self.id))
            if subtree:
                table = await quota.table_of("FileFolder")
                await grunt.get_session().execute(
                    table.update()
                    .where(table.c.name.in_(subtree))
                    .values(space_user=self.space_user)
                )

    @classmethod
    async def tree_sort_children(
        cls,
        session: Any,
        children: list[dict[str, Any]],
        *,
        parent: dict[str, Any] | None,
        sort_by: str | None,
        sort_order: str,
    ) -> list[dict[str, Any]]:
        """Roots: your own home first, shown as «My files»; other spaces
        (System Manager, shared folders) after it."""
        if parent is not None:
            return children
        me = grunt.get_user().email
        for node in children:
            if node.get("is_home") and node.get("space_user") == me:
                node["display_title"] = _("My files")
        return sorted(children, key=lambda n: "display_title" not in n)

    async def before_delete(self) -> None:
        """Only an empty folder can go - files and subfolders are moved out first."""
        if self.is_home:
            grunt.throw(_("A home folder can't be deleted"))
        if await grunt.db.count("File", {"folder": self.name}):
            grunt.throw(_("The folder is not empty: move or delete its files first"))
        if await grunt.db.count("FileFolder", {"parent_folder": self.name}):
            grunt.throw(_("The folder has subfolders: move or delete them first"))


async def require_folder_write(folder: dict[str, Any]) -> None:
    """403 unless the current user may put things into *folder* (their own
    space, a folder shared with them for writing, or System Manager)."""
    from grunt.permissions.rbac import permission_checker

    meta = await grunt.get_meta("FileFolder")
    assert meta is not None
    if not await permission_checker.check(grunt.get_user(), meta, "write", folder):
        grunt.throw(
            _("No access to the folder “%(folder)s”") % {"folder": folder.get("folder_name")},
            "PERMISSION_DENIED",
        )


async def _subtree_size(folder: str) -> int:
    from sqlalchemy import func, select

    subtree = await expand_tree_values("FileFolder", {folder})
    files = await quota.table_of("File")
    total = await grunt.get_session().scalar(
        select(func.coalesce(func.sum(files.c.file_size), 0)).where(files.c.folder.in_(subtree))
    )
    return int(total or 0)


@whitelist()
async def get_home_folder() -> dict[str, Any]:
    """Whitelisted method: the current user's home folder, created on first use."""
    user = grunt.get_user()
    row = await grunt.db.get_value(
        "FileFolder",
        {"space_user": user.email, "is_home": 1},
        ["name", "folder_name"],
        as_dict=True,
    )
    if row:
        return row
    title = await grunt.db.get_value("User", user.email, "full_name") or user.email
    doc = await grunt.new_doc(
        "FileFolder", {"folder_name": title, "is_home": 1, "space_user": user.email}
    )
    return {"name": doc["name"], "folder_name": doc["folder_name"]}


@whitelist()
async def get_storage_usage(user: str | None = None) -> dict[str, Any]:
    """Whitelisted method: ``{used, quota}`` in bytes for a space (``quota``
    is ``None`` when unlimited). Another user's space - System Manager only."""
    current = grunt.get_user()
    space = user or current.email
    if space != current.email and not user_has_roles(current, ["System Manager"]):
        grunt.throw(_("Not permitted"), "PERMISSION_DENIED")
    return {"used": await quota.space_usage(space), "quota": await quota.space_quota(space)}


# Explorer commands: copy and delete whole selections (move is a plain save of
# File.folder / FileFolder.parent_folder - see move_tree_node).

_MANY = 10_000


@whitelist()
async def copy_items(
    target: str, files: list[str] | None = None, folders: list[str] | None = None
) -> dict[str, int]:
    """Whitelisted method: copy files and folders (with all they hold) into *target*.

    A copy is a new File row over the same stored content - no disk space,
    but it counts against the target space's quota. Names already taken in
    *target* get « (копія)», « (копія 2)»…
    """
    folder = await grunt.db.get_value("FileFolder", target, "*")
    if folder is None:
        grunt.throw(_("Folder “%(folder)s” not found") % {"folder": target})
    await require_folder_write(folder)
    copied = 0
    for name in files or []:
        await _copy_file(await grunt.get_doc("File", name), target)
        copied += 1
    for name in folders or []:
        if target in await expand_tree_values("FileFolder", {name}):
            grunt.throw(_("A folder can't be copied into itself"))
        copied += await _copy_folder(await grunt.get_doc("FileFolder", name), target)
    return {"copied": copied}


async def _copy_file(row: dict[str, Any], target: str) -> None:
    from grunt.storage import files

    taken = {
        r["file_name"]
        for r in await grunt.db.get_all(
            "File", filters={"folder": target}, fields=["file_name"], limit=_MANY
        )
    }
    await files.create_file(
        row["content_hash"],
        row["file_size"] or 0,
        _free_name(row["file_name"], taken),
        row["content_type"],
        folder=target,
    )


async def _copy_folder(row: dict[str, Any], target: str) -> int:
    taken = {
        r["folder_name"]
        for r in await grunt.db.get_all(
            "FileFolder", filters={"parent_folder": target}, fields=["folder_name"], limit=_MANY
        )
    }
    copy = await grunt.new_doc(
        "FileFolder",
        {"folder_name": _free_name(row["folder_name"], taken), "parent_folder": target},
    )
    copied = 1
    for file in await grunt.get_list(
        "File",
        filters={"folder": row["name"]},
        fields=["name", "file_name", "file_size", "content_type", "content_hash"],
        limit=_MANY,
    ):
        await _copy_file(file, copy["name"])
        copied += 1
    for sub in await grunt.get_list(
        "FileFolder",
        filters={"parent_folder": row["name"]},
        fields=["name", "folder_name"],
        limit=_MANY,
    ):
        copied += await _copy_folder(sub, copy["name"])
    return copied


def _free_name(name: str, taken: set[str]) -> str:
    """*name*, or «name (копія).ext», «name (копія 2).ext»… when it's taken."""
    if name not in taken:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    suffix = f".{ext}" if ext else ""
    n = 1
    while True:
        copy = pgettext("file name", "copy")
        label = copy if n == 1 else f"{copy} {n}"
        candidate = f"{stem} ({label}){suffix}"
        if candidate not in taken:
            return candidate
        n += 1


@whitelist()
async def delete_items(
    files: list[str] | None = None, folders: list[str] | None = None
) -> dict[str, int]:
    """Whitelisted method: delete files and folders - a folder with everything in it.

    Each File / FileFolder goes through the normal delete (permissions, the
    trash), deepest first so every folder is empty by the time it goes.
    """
    deleted = 0
    for name in files or []:
        await grunt.delete_doc("File", name)
        deleted += 1
    for name in folders or []:
        deleted += await _delete_folder(name)
    return {"deleted": deleted}


async def _delete_folder(name: str) -> int:
    await grunt.get_doc("FileFolder", name)  # 403 / 404 before touching anything inside
    deleted = 0
    for sub in await grunt.db.get_all(
        "FileFolder", filters={"parent_folder": name}, fields=["name"], limit=_MANY
    ):
        deleted += await _delete_folder(sub["name"])
    for file in await grunt.db.get_all(
        "File", filters={"folder": name}, fields=["name"], limit=_MANY
    ):
        await grunt.delete_doc("File", file["name"])
        deleted += 1
    await grunt.delete_doc("FileFolder", name)
    return deleted + 1
