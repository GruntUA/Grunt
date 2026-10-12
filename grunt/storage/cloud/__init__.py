"""External cloud storage - ``StorageRemote`` connections run through rclone.

* :mod:`grunt.storage.cloud.rclone` - one remote's rclone config + file operations
  (any app can use it: ``async with Rclone(await load_remote(name)) as rc``);
* :mod:`grunt.storage.cloud.providers` - Google Drive, Dropbox, OneDrive, MEGA, S3,
  WebDAV, SFTP, SMB, a server folder or any other rclone backend;
* :mod:`grunt.storage.cloud.backups` - backup sets uploaded to remotes, rotated
  there, fetched back;
* :mod:`grunt.storage.cloud.files` - blobs moved off the server disk, read back
  through a local cache;
* :mod:`grunt.storage.cloud.oauth` - signing in to Drive/Dropbox/OneDrive.

Secrets live in the row as entered (rclone needs them in clear) and never go
back to a client: :func:`mask_secrets` replaces them on every API read, and
the controller keeps the stored value when a save sends the mask back.
Backend code reads rows with :func:`load_remote` (``grunt.db``, no hooks).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import grunt
from grunt import _, log, log_error
from grunt.storage.cloud.rclone import Rclone, RemoteError

__all__ = [
    "MASK",
    "SECRET_FIELDS",
    "Rclone",
    "RemoteError",
    "backup_remotes",
    "files_remote",
    "load_remote",
    "record_status",
]

MASK = "••••••••"
SECRET_FIELDS = (
    "client_secret",
    "oauth_token",
    "secret_access_key",
    "password",
    "ssh_private_key",
    "encryption_password",
    "encryption_salt",
)


async def load_remote(name: str) -> dict[str, Any]:
    """The ``StorageRemote`` row with its real secrets; RemoteError when there is none."""
    row = await grunt.db.get_value("StorageRemote", name, "*")
    if not row:
        raise RemoteError(_("Storage “%(name)s” not found") % {"name": name})
    return dict(row)


async def backup_remotes() -> list[dict[str, Any]]:
    """Enabled remotes that receive backups."""
    return await grunt.db.get_all(
        "StorageRemote", filters={"enabled": 1, "use_for_backups": 1}, fields=["*"], limit=None
    )


async def files_remote() -> dict[str, Any] | None:
    """The enabled remote old files are moved to, if any (there is at most one)."""
    rows = await grunt.db.get_all(
        "StorageRemote", filters={"enabled": 1, "use_for_files": 1}, fields=["*"], limit=1
    )
    return rows[0] if rows else None


def _mask(row: Any) -> None:
    if isinstance(row, dict):
        for field in SECRET_FIELDS:
            if row.get(field):
                row[field] = MASK


async def mask_secrets(**kwargs: Any) -> None:
    """``after_read`` of ``StorageRemote``: no secret ever leaves the server."""
    _mask(kwargs.get("doc"))
    data = kwargs.get("data")
    for row in data if isinstance(data, list) else [data]:
        _mask(row)


async def record_status(
    remote: dict[str, Any], error: BaseException | str | None, **values: Any
) -> None:
    """Store the outcome of an operation on *remote* (plus *values*), commit.

    A failure goes to ErrorLog; System Managers are notified when the remote
    turns from OK to Error (not on every failing night).
    """
    name = remote["name"]
    now = datetime.now(UTC)
    if error is None:
        values |= {"last_status": "OK", "last_error": None, "last_check_at": now}
    else:
        message = str(error)
        values |= {"last_status": "Error", "last_error": message, "last_check_at": now}
        await log_error(
            exc=error if isinstance(error, BaseException) else None,
            title=(_("Cloud storage “%(name)s”: %(error)s") % {"name": name, "error": message})[
                :150
            ],
            message=message,
            context="Background Task",
            reference_doctype="StorageRemote",
            reference_name=name,
        )
        if remote.get("last_status") != "Error":
            await _notify_managers(name, message)
    await grunt.db.set_value("StorageRemote", name, values)
    remote.update(values)
    await grunt.get_session().commit()


async def _notify_managers(name: str, message: str) -> None:
    from grunt.notification.service import notification_service

    session = grunt.get_session()
    try:
        users = await notification_service._resolve_role_recipients(["System Manager"], session)
        for user in users:
            await notification_service.notify(
                session,
                user=user,
                doctype="StorageRemote",
                doc_id=name,
                subject=_("Cloud storage “%(name)s” is failing") % {"name": name},
                message=message,
            )
    except Exception:
        log.warning("cloud.notify_failed", remote=name, exc_info=True)
