from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from grunt.backups import BackupSet, delete_backup, get_backup, list_backups
from grunt.backups.api import download_url
from grunt.metadata.virtual import VirtualDocType
from grunt.monitoring.health import human_size


def _site() -> str:
    from grunt.site.manager import site_manager

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


class BackupController(VirtualDocType):
    """The backup sets on disk — made by the scheduler or «Створити зараз»."""

    async def get_list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: str = "name",
        sort_order: str = "desc",
        search: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        site = _site()
        rows = [_row(site, b) for b in list_backups(site)]
        if search:
            rows = self.apply_search(rows, search, ["name"])
        rows = self.apply_sort(rows, sort_by if sort_by != "modified_at" else "name", sort_order)
        return self.build_response(rows, page, per_page)

    async def get(self, doc_id: str, **kwargs: Any) -> dict[str, Any]:
        site = _site()
        backup = get_backup(site, doc_id)
        if backup is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Резервну копію не знайдено")
        return _row(site, backup)

    async def delete(self, doc_id: str, **kwargs: Any) -> None:
        delete_backup(_site(), doc_id)

    async def create(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(
            status.HTTP_405_METHOD_NOT_ALLOWED, "Копію створює кнопка «Створити зараз»"
        )

    async def update(self, doc_id: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Резервну копію не можна змінити")
