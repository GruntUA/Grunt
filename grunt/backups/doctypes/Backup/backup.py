from typing import Any

from grunt.backups import BackupSet, delete_backup, get_backup, list_backups
from grunt.backups.api import download_url
from grunt.document.base import Document
from grunt.i18n import N_
from grunt.monitoring.health import human_size
from grunt.query.query import Query
from grunt.site.manager import site_manager
from grunt.storage.cloud.backups import load_state
from grunt.store import DELETE, VirtualStore


def _site() -> str:
    return site_manager.get_active_site()


def _row(site: str, backup: BackupSet, cloud: dict[str, dict[str, str]]) -> dict[str, Any]:
    def size(kind: str) -> str:
        return human_size(backup.size(kind)) if kind in backup.files else ""

    return {
        "name": backup.id,
        "created_at": backup.created_at.isoformat(),
        "total_size": human_size(backup.size()),
        "database_size": size("database"),
        "files_size": size("files"),
        "has_config": "config" in backup.files,
        "in_cloud": ", ".join(sorted(cloud.get(backup.id, {}))),
        **{f"{kind}_url": download_url(site, path.name) for kind, path in backup.files.items()},
    }


class BackupStore(VirtualStore):
    """The backup sets on disk. Created only by the Create now button and never
    changed: insert and update are left unsupported."""

    capabilities = frozenset({DELETE})
    not_supported_message = N_(
        "Backups are created with the Create now button and cannot be changed"
    )

    async def rows(self, query: Query) -> list[dict[str, Any]]:
        site = _site()
        cloud = load_state(site)
        return [_row(site, b, cloud) for b in list_backups(site)]

    async def get(self, name: str, *, expand: list[str] | None = None) -> dict[str, Any] | None:
        site = _site()
        backup = get_backup(site, name)
        return None if backup is None else _row(site, backup, load_state(site))

    async def delete(self, name: str, *, before: dict[str, Any]) -> None:
        delete_backup(_site(), name)


class Backup(Document):
    """The backup sets on disk - made by the scheduler or «Створити зараз»."""

    store_class = BackupStore
