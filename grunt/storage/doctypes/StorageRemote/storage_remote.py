"""Controller for StorageRemote - a connection to external storage (grunt.storage.cloud)."""

import contextlib
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from grunt.api.context import whitelist
from grunt.db.api import GruntDB
from grunt.document.base import Document
from grunt.errors import throw
from grunt.i18n import _
from grunt.local import require_session, user_email
from grunt.site.manager import site_manager
from grunt.storage.cloud import MASK, SECRET_FIELDS, RemoteError, load_remote, record_status
from grunt.storage.cloud.rclone import Rclone, config_text
lazy from grunt.storage.cloud.backups import forget_remote, list_remote_backups
lazy from grunt.storage.cloud.providers import get_provider
lazy from grunt.storage.cloud.tasks import upload_latest_backup
lazy from grunt.utils.sizes import human_size

_db = GruntDB()  # stateless: reads through the context's session

# Changing any of these makes what is already in the storage unreachable
# (another place, another key) - not while files live there.
_LOCATION_FIELDS = (
    "provider",
    "root_folder",
    "encrypt",
    "encryption_password",
    "encryption_salt",
    "rclone_type",
)
# A fresh name per run: Drive keeps several files under one name, and a probe
# left behind by an earlier run (a retried upload, a failed delete) would be
# read back together with this one.
_PROBE = ".grunt-connection-test-{}"


class StorageRemote(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    title: str  # Name
    provider: str | None = None  # Storage type
    enabled: bool | None = None  # Enabled
    root_folder: str | None = None  # Root folder
    oauth_account: str | None = None  # Connected account
    oauth_connected_at: datetime | None = None  # Connected at
    client_id: str | None = None  # Client ID
    client_secret: str | None = None  # Client secret
    oauth_token: str | None = None  # OAuth token
    oauth_extra: str | None = None  # OAuth extra
    s3_provider: str | None = None  # S3 provider
    endpoint: str | None = None  # Address (URL)
    region: str | None = None  # Region
    webdav_vendor: str | None = None  # WebDAV server
    host: str | None = None  # Host
    port: int | None = None  # Port
    domain: str | None = None  # Domain
    access_key_id: str | None = None  # Access key ID
    secret_access_key: str | None = None  # Secret access key
    username: str | None = None  # User
    password: str | None = None  # Password
    ssh_private_key: str | None = None  # SSH private key
    rclone_type: str | None = None  # rclone backend
    rclone_options: str | None = None  # rclone options
    encrypt: bool | None = None  # Encrypt before sending
    encryption_password: str | None = None  # Encryption password
    encryption_salt: str | None = None  # Second password (salt)
    last_status: str | None = None  # Status
    last_check_at: datetime | None = None  # Last checked
    quota: str | None = None  # Space
    last_error: str | None = None  # Last error
    use_for_backups: bool | None = None  # Upload backups here
    backup_keep: int | None = None  # Copies to keep here
    last_backup_at: datetime | None = None  # Last upload
    last_backup_id: str | None = None  # Last uploaded set
    use_for_files: bool | None = None  # Move old files here
    offload_after_days: int | None = None  # Older than, days
    offload_min_size_kb: int | None = None  # Larger than, KB
    offload_public: bool | None = None  # Public files too
    offload_doctypes: str | None = None  # Only files of
    cache_size_mb: int | None = None  # Local cache, MB
    offloaded_files: int | None = None  # Files in the storage
    offloaded_size: str | None = None  # Their size

    # end: auto-generated types

    async def before_save(self) -> None:
        stored = await _db.get_value("StorageRemote", self.name, "*") if self.name else None
        self._keep_masked_secrets(stored)
        if stored:
            await self._guard_location(stored)
        if self.use_for_files and self.enabled:
            other = await _db.get_all(
                "StorageRemote",
                filters={"use_for_files": True, "enabled": True, "name__ne": self.name or ""},
                pluck="title",
                limit=1,
            )
            if other:
                throw(
                    _("Files are already moved to “%(name)s”; only one storage can hold files")
                    % {"name": other[0]}
                )

    def _keep_masked_secrets(self, stored: dict[str, Any] | None) -> None:
        """Reads hand out MASK instead of secrets - saving it back means "unchanged"."""
        for field in SECRET_FIELDS:
            value = self.get(field)
            if value == MASK or (value in (None, "") and field == "oauth_token"):
                self.data[field] = (stored or {}).get(field)

    async def _guard_location(self, stored: dict[str, Any]) -> None:
        changed = [f for f in _LOCATION_FIELDS if (self.get(f) or None) != (stored.get(f) or None)]
        if changed and await _db.count("File", {"storage_remote": self.name}):
            throw(
                _(
                    "Files are kept in this storage: return them to the server first "
                    "(Files → Return all files), then change where or how they are stored"
                )
            )

    async def before_delete(self) -> None:
        if await _db.count("File", {"storage_remote": self.name}):
            throw(_("Files are kept in this storage: return them to the server before deleting it"))

    async def after_delete(self) -> None:

        forget_remote(site_manager.get_active_site(), str(self.name))


def _user() -> str:
    return user_email()


async def _remote(name: str) -> dict[str, Any]:
    try:
        return await load_remote(name)
    except RemoteError as exc:
        raise HTTPException(404, str(exc)) from exc


@whitelist(perm="grunt.manage_storage")
async def test_connection(name: str) -> dict[str, Any]:
    """Create the root folder, write + delete a probe file, read the quota."""

    remote = await _remote(name)
    await require_session().commit()
    quota = ""
    try:
        async with Rclone(remote) as rc:
            await rc.mkdir()
            probe = _PROBE.format(uuid.uuid4().hex)
            try:
                await rc.put_bytes(b"grunt", probe)
                if await rc.cat(probe) != b"grunt":
                    raise RemoteError(_("The test file read back differs from what was written"))
            finally:
                with contextlib.suppress(RemoteError):
                    await rc.delete_file(probe)
            about = await rc.about()
        if about and about.get("total"):
            quota = _("%(free)s free of %(total)s") % {
                "free": human_size(about.get("free") or 0),
                "total": human_size(about["total"]),
            }
        elif about and about.get("used") is not None:
            quota = _("%(used)s used") % {"used": human_size(about["used"])}
    except RemoteError as exc:
        await record_status(remote, exc)
        return {"ok": False, "error": str(exc)}
    await record_status(remote, None, quota=quota or None)
    return {"ok": True, "quota": quota}


@whitelist(perm="grunt.manage_storage")
async def show_config(name: str) -> dict[str, str]:
    """The remote as rclone.conf text (secrets obscured the rclone way)."""
    try:
        return {"config": config_text(await _remote(name))}
    except RemoteError as exc:
        raise HTTPException(422, str(exc)) from exc


@whitelist(perm="grunt.manage_storage")
async def oauth_help(name: str) -> dict[str, str]:
    """The ``rclone authorize`` command for this remote's provider."""

    remote = await _remote(name)
    return {"command": get_provider(remote.get("provider")).authorize_command}


@whitelist(perm="grunt.manage_backups")
async def list_backups(name: str) -> list[dict[str, Any]]:
    """Backup sets kept in the remote (newest first)."""

    remote = await _remote(name)
    await require_session().commit()
    try:
        async with Rclone(remote) as rc:
            rows = await list_remote_backups(rc, site_manager.get_active_site())
    except RemoteError as exc:
        raise HTTPException(422, str(exc)) from exc
    return [
        {
            **row,
            "name": row["id"],
            "size": human_size(row["size"]),
            "kinds": ", ".join(_(k.capitalize()) for k in row["kinds"]),
            "on_server": _("yes") if row["on_server"] else "",
        }
        for row in rows
    ]


@whitelist(perm="grunt.manage_backups")
async def fetch_backup(name: str, backup_id: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import fetch_backup as job

    await _remote(name)
    await job.kiq(name, backup_id, user=_user())
    return {"queued": True}


@whitelist(perm="grunt.manage_backups")
async def upload_latest(name: str) -> dict[str, bool]:

    await _remote(name)
    await upload_latest_backup.kiq(name, user=_user())
    return {"queued": True}


@whitelist(perm="grunt.manage_storage")
async def offload_now(name: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import offload_now as job

    await _remote(name)
    await job.kiq(name, user=_user())
    return {"queued": True}


@whitelist(perm="grunt.manage_storage")
async def recall_files(name: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import recall_files as job

    await _remote(name)
    await job.kiq(name, user=_user())
    return {"queued": True}
