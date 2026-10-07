from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from grunt import _
from grunt.backups import BackupSet, delete_backup, get_backup, list_backups
from grunt.backups.api import download_url
from grunt.document.base import BaseDocument, DocumentList
from grunt.document.in_memory import apply_search, apply_sort, build_response
from grunt.monitoring.health import human_size
from grunt.site.manager import site_manager


def _site() -> str:
    return site_manager.get_active_site()


def _row(site: str, backup: BackupSet) -> dict[str, Any]:
    def size(kind: str) -> str:
        return human_size(backup.size(kind)) if kind in backup.files else ""

    return {
        "name": backup.id,
        "created_at": backup.created_at.isoformat(),
        "total_size": human_size(backup.size()),
        "database_size": size("database"),
        "files_size": size("files"),
        "has_config": "config" in backup.files,
        **{f"{kind}_url": download_url(site, path.name) for kind, path in backup.files.items()},
    }


class BackupController(BaseDocument):
    """The backup sets on disk - made by the scheduler or «Створити зараз».

    Created only by the Create now button and never changed: insert and
    update are left unsupported.
    """

    @classmethod
    async def get_list(
        cls,
        doctype: str,
        *,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "desc",
        search: str | None = None,
        **kwargs: Any,
    ) -> DocumentList:
        site = _site()
        rows = [_row(site, b) for b in list_backups(site)]
        if search:
            rows = apply_search(rows, search, ["name"])
        rows = apply_sort(rows, sort_by if sort_by != "modified_at" else "name", sort_order)
        return build_response(rows, page, per_page)

    async def load_from_db(self, *, expand: list[str] | None = None) -> None:
        site = _site()
        backup = get_backup(site, str(self.name))
        if backup is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, _("Backup not found"))
        self.data = _row(site, backup)

    async def db_delete(self) -> None:
        delete_backup(_site(), str(self.name))
