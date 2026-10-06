"""Moving a site from the shared file library to personal spaces.

Before personal spaces every folder and unfiled file was visible to everyone.
:func:`assign_spaces` gives each of them an owner: a root folder moves (with
its subtree) into its author's home folder, an unfiled library file into its
uploader's. Quotas are not applied - an over-quota space just can't take new
files until it is cleaned up.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

import grunt
from grunt.permissions.user_permissions import expand_tree_values
from grunt.storage.quota import table_of


async def assign_spaces(*, apply: bool, fallback_owner: str | None = None) -> dict[str, Any]:
    """Plan (and with *apply*, carry out) the move; return what goes where.

    An owner who is no longer a user falls back to *fallback_owner*; without
    one such items are reported and left alone.
    """
    folders = await table_of("FileFolder")
    files = await table_of("File")
    session = grunt.get_session()
    users = set((await session.execute(select((await table_of("User")).c.name))).scalars())

    def owner_of(*candidates: str | None) -> str | None:
        for email in candidates:
            if email and email in users:
                return email
        return fallback_owner if fallback_owner in users else None

    report: dict[str, Any] = {"folders": [], "files": [], "skipped": []}
    homes: dict[str, str] = {}

    async def home_of(email: str) -> str:
        if email not in homes:
            name = await grunt.db.get_value("FileFolder", {"space_user": email, "is_home": 1})
            if not name and apply:
                title = await grunt.db.get_value("User", email, "full_name") or email
                doc = await grunt.new_doc(
                    "FileFolder", {"folder_name": title, "is_home": 1, "space_user": email}
                )
                name = doc["name"]
            homes[email] = name or f"<home of {email}>"
        return homes[email]

    roots = (
        await session.execute(
            select(folders.c.name, folders.c.folder_name, folders.c.owner).where(
                or_(folders.c.parent_folder.is_(None), folders.c.parent_folder == ""),
                or_(folders.c.is_home.is_(None), folders.c.is_home == 0),
            )
        )
    ).all()
    for name, title, author in roots:
        owner = owner_of(author)
        if owner is None:
            report["skipped"].append(f"folder {title} ({author})")
            continue
        home = await home_of(owner)
        report["folders"].append({"folder": title, "owner": owner})
        if apply:
            subtree = await expand_tree_values("FileFolder", {name})
            await session.execute(
                folders.update().where(folders.c.name.in_(subtree)).values(space_user=owner)
            )
            await session.execute(
                folders.update().where(folders.c.name == name).values(parent_folder=home)
            )

    unfiled = (
        await session.execute(
            select(files.c.name, files.c.file_name, files.c.uploaded_by, files.c.owner).where(
                or_(files.c.folder.is_(None), files.c.folder == ""),
                or_(files.c.attached_to_doctype.is_(None), files.c.attached_to_doctype == ""),
            )
        )
    ).all()
    for name, title, uploader, author in unfiled:
        owner = owner_of(uploader, author)
        if owner is None:
            report["skipped"].append(f"file {title} ({uploader or author})")
            continue
        home = await home_of(owner)
        report["files"].append({"file": title, "owner": owner})
        if apply:
            await session.execute(
                files.update().where(files.c.name == name).values(folder=home, is_public=False)
            )

    if apply:
        await session.execute(
            files.update()
            .where(files.c.folder.is_not(None), files.c.folder != "")
            .values(is_public=False)
        )
        await session.commit()
    return report
