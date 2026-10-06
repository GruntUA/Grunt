"""Personal storage quotas - how much a user's file space (their home folder
and everything in it) may hold.

The limit is ``User.storage_quota_mb`` when set, else
``SystemSettings.personal_storage_quota_mb``; 0 there means no limit. Usage is
the logical size of the files in the space - shared blobs count for every row
that lists them, so a user's number never depends on other people's files.
Document attachments and not-yet-filed uploads live outside any space and
don't count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

import grunt
from grunt import _
from grunt.site.settings import get_setting

if TYPE_CHECKING:
    from sqlalchemy import Table

_MB = 1024 * 1024


async def table_of(doctype: str) -> Table:
    meta = await grunt.get_meta(doctype)
    assert meta is not None, doctype
    return meta.table


async def space_quota(space_user: str) -> int | None:
    """The space's limit in bytes, ``None`` when unlimited."""
    own = await grunt.db.get_value("User", space_user, "storage_quota_mb")
    mb = own if own and own > 0 else await get_setting("personal_storage_quota_mb", 1024)
    return int(mb) * _MB if mb and mb > 0 else None


async def space_usage(space_user: str) -> int:
    """Bytes held by the files in *space_user*'s folders."""
    files = await table_of("File")
    folders = await table_of("FileFolder")
    in_space = select(folders.c.name).where(folders.c.space_user == space_user)
    total = await grunt.get_session().scalar(
        select(func.coalesce(func.sum(files.c.file_size), 0)).where(files.c.folder.in_(in_space))
    )
    return int(total or 0)


async def ensure_room(space_user: str, size: int) -> None:
    """Refuse to put *size* more bytes into a space that can't hold them."""
    quota = await space_quota(space_user)
    if quota is None:
        return
    used = await space_usage(space_user)
    if used + size > quota:
        grunt.throw(
            _("Not enough space: %(used)s MB of %(quota)s MB used, the file needs %(size)s MB")
            % {"used": _mb(used), "quota": _mb(quota), "size": _mb(size)}
        )


def _mb(size: int) -> str:
    return f"{size / _MB:.1f}".removesuffix(".0")
