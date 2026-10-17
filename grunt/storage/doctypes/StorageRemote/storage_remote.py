"""Controller for StorageRemote - a connection to external storage (grunt.storage.cloud)."""

import contextlib
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException

import grunt
from grunt import _, whitelist
from grunt.document.base import Document
from grunt.site.manager import site_manager
from grunt.storage.cloud import MASK, SECRET_FIELDS, RemoteError, load_remote, record_status
from grunt.storage.cloud.rclone import Rclone, config_text
lazy from grunt.monitoring.health import human_size
lazy from grunt.storage.cloud.backups import forget_remote, list_remote_backups
lazy from grunt.storage.cloud.providers import get_provider
lazy from grunt.storage.cloud.tasks import upload_latest_backup

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

    title: str | None  # Name
    provider: str | None  # Storage type
    enabled: bool | None  # Enabled
    root_folder: str | None  # Root folder
    oauth_account: str | None  # Connected account
    oauth_connected_at: datetime | None  # Connected at
    paste_token: None  # Paste a token from rclone
    client_id: str | None  # Client ID
    client_secret: str | None  # Client secret
    authorize: None  # Sign in through the browser
    oauth_token: str | None  # OAuth token
    oauth_extra: str | None  # OAuth extra
    s3_provider: str | None  # S3 provider
    endpoint: str | None  # Address (URL)
    region: str | None  # Region
    webdav_vendor: str | None  # WebDAV server
    host: str | None  # Host
    port: int | None  # Port
    domain: str | None  # Domain
    access_key_id: str | None  # Access key ID
    secret_access_key: str | None  # Secret access key
    username: str | None  # User
    password: str | None  # Password
    ssh_private_key: str | None  # SSH private key
    rclone_type: str | None  # rclone backend
    rclone_options: str | None  # rclone options
    encrypt: bool | None  # Encrypt before sending
    encryption_password: str | None  # Encryption password
    encryption_salt: str | None  # Second password (salt)
    test_connection: None  # Test connection
    show_config: None  # Show rclone config
    last_status: str | None  # Status
    last_check_at: datetime | None  # Last checked
    quota: str | None  # Space
    last_error: str | None  # Last error
    use_for_backups: bool | None  # Upload backups here
    backup_keep: int | None  # Copies to keep here
    upload_latest: None  # Upload the latest backup now
    browse_backups: None  # Backups in this storage
    last_backup_at: datetime | None  # Last upload
    last_backup_id: str | None  # Last uploaded set
    use_for_files: bool | None  # Move old files here
    offload_after_days: int | None  # Older than, days
    offload_min_size_kb: int | None  # Larger than, KB
    offload_public: bool | None  # Public files too
    offload_doctypes: str | None  # Only files of
    cache_size_mb: int | None  # Local cache, MB
    offloaded_files: int | None  # Files in the storage
    offloaded_size: str | None  # Their size
    offload_now: None  # Move files now
    recall_files: None  # Return all files to the server

    # end: auto-generated types

    async def before_save(self) -> None:
        stored = await grunt.db.get_value("StorageRemote", self.name, "*") if self.name else None
        self._keep_masked_secrets(stored)
        if stored:
            await self._guard_location(stored)
        if self.use_for_files and self.enabled:
            other = await grunt.db.get_all(
                "StorageRemote",
                filters={"use_for_files": 1, "enabled": 1, "name__ne": self.name or ""},
                pluck="title",
                limit=1,
            )
            if other:
                grunt.throw(
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
        if changed and await grunt.db.count("File", {"storage_remote": self.name}):
            grunt.throw(
                _(
                    "Files are kept in this storage: return them to the server first "
                    "(Files → Return all files), then change where or how they are stored"
                )
            )

    async def before_delete(self) -> None:
        if await grunt.db.count("File", {"storage_remote": self.name}):
            grunt.throw(
                _("Files are kept in this storage: return them to the server before deleting it")
            )

    async def after_delete(self) -> None:

        forget_remote(site_manager.get_active_site(), str(self.name))


def _user() -> str:
    return grunt.get_user().email


async def _remote(name: str) -> dict[str, Any]:
    try:
        return await load_remote(name)
    except RemoteError as exc:
        raise HTTPException(404, str(exc)) from exc


@whitelist(roles=["System Manager"])
async def test_connection(name: str) -> dict[str, Any]:
    """Create the root folder, write + delete a probe file, read the quota."""

    remote = await _remote(name)
    await grunt.get_session().commit()
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


@whitelist(roles=["System Manager"])
async def show_config(name: str) -> dict[str, str]:
    """The remote as rclone.conf text (secrets obscured the rclone way)."""
    try:
        return {"config": config_text(await _remote(name))}
    except RemoteError as exc:
        raise HTTPException(422, str(exc)) from exc


@whitelist(roles=["System Manager"])
async def oauth_help(name: str) -> dict[str, str]:
    """The ``rclone authorize`` command for this remote's provider."""

    remote = await _remote(name)
    return {"command": get_provider(remote.get("provider")).authorize_command}


@whitelist(roles=["System Manager"])
async def list_backups(name: str) -> list[dict[str, Any]]:
    """Backup sets kept in the remote (newest first)."""

    remote = await _remote(name)
    await grunt.get_session().commit()
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


@whitelist(roles=["System Manager"])
async def fetch_backup(name: str, backup_id: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import fetch_backup as job

    await _remote(name)
    await job.kiq(name, backup_id, user=_user())
    return {"queued": True}


@whitelist(roles=["System Manager"])
async def upload_latest(name: str) -> dict[str, bool]:

    await _remote(name)
    await upload_latest_backup.kiq(name, user=_user())
    return {"queued": True}


@whitelist(roles=["System Manager"])
async def offload_now(name: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import offload_now as job

    await _remote(name)
    await job.kiq(name, user=_user())
    return {"queued": True}


@whitelist(roles=["System Manager"])
async def recall_files(name: str) -> dict[str, bool]:
    from grunt.storage.cloud.tasks import recall_files as job

    await _remote(name)
    await job.kiq(name, user=_user())
    return {"queued": True}
