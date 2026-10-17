"""Backup sets in cloud storage.

After a set is made (grunt.backups.tasks) it goes to every enabled remote
with «Upload backups here», into ``<root>/backups/<site>/`` under the same
file names, and each remote keeps its own number of sets. Which remotes hold
which set is remembered in ``backups/.cloud.json`` for the Backups list - no
network round-trip on every page load. A set can be fetched back into
``backups/`` from any remote; restoring stays ``grunt db restore``.
"""

import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grunt
from grunt import _, log
from grunt.backups import _NAME, BackupSet, backups_dir, get_backup, list_backups
from grunt.storage.cloud import RemoteError, backup_remotes, record_status
from grunt.storage.cloud.rclone import Rclone
lazy from grunt.progress import Progress

STATE_FILE = ".cloud.json"


def remote_dir(site: str) -> str:
    return f"backups/{site}"


# Which remote holds which set


def _state_path(site: str) -> Path:
    return backups_dir(site) / STATE_FILE


def load_state(site: str) -> dict[str, dict[str, str]]:
    """``{backup_id: {remote: uploaded_at}}``."""
    try:
        return json.loads(_state_path(site).read_text())
    except OSError, ValueError:
        return {}


def _save_state(site: str, state: dict[str, dict[str, str]]) -> None:
    path = _state_path(site)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True))
    os.replace(tmp, path)


def _mark(site: str, remote: str, uploaded: list[str], removed: list[str]) -> None:
    state = load_state(site)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for backup_id in uploaded:
        state.setdefault(backup_id, {})[remote] = now
    for backup_id in removed:
        with contextlib.suppress(KeyError):
            del state[backup_id][remote]
    _save_state(site, {k: v for k, v in state.items() if v})


def forget_remote(site: str, remote: str) -> None:
    """A deleted / renamed remote no longer counts as holding anything."""
    _mark(site, remote, [], list(load_state(site)))


# Listing a remote


def _group(entries: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """``{backup_id: {kind: entry}}`` of files named like our sets."""
    sets: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in entries:
        m = _NAME.match(entry.get("Path") or "")
        if m:
            sets.setdefault(m.group(1), {})[m.group(2)] = entry
    return sets


async def list_remote_backups(rc: Rclone, site: str) -> list[dict[str, Any]]:
    """Sets in the remote, newest first."""
    local = {b.id for b in _local_sets(site)}
    rows = []
    for backup_id, kinds in sorted(_group(await rc.list(remote_dir(site))).items(), reverse=True):
        rows.append(
            {
                "id": backup_id,
                "created_at": datetime.strptime(backup_id, "%Y%m%d-%H%M%S")
                .replace(tzinfo=UTC)
                .isoformat(),
                "kinds": sorted(kinds),
                "size": sum(int(e.get("Size") or 0) for e in kinds.values()),
                "on_server": backup_id in local,
            }
        )
    return rows


def _local_sets(site: str) -> list[BackupSet]:

    return list_backups(site)


async def rotate_remote(rc: Rclone, site: str, keep: int) -> list[str]:
    """Delete all but the *keep* newest sets in the remote; returns their ids."""
    sets = _group(await rc.list(remote_dir(site)))
    removed = sorted(sets, reverse=True)[max(keep, 1) :]
    paths = [entry["Path"] for backup_id in removed for entry in sets[backup_id].values()]
    await rc.delete_files(paths, remote_dir(site))
    return removed


# Uploading


async def upload_backup(
    site: str, backup: BackupSet, remote: dict[str, Any], progress: Progress | None = None
) -> list[str]:
    """Upload *backup* to *remote* and rotate there; returns the rotated-out ids.

    Raises RemoteError; the caller records the outcome.
    """
    base = 0
    async with Rclone(remote) as rc:
        for path in sorted(backup.files.values(), key=lambda p: p.stat().st_size):
            await rc.put_file(
                path, f"{remote_dir(site)}/{path.name}", progress=progress, progress_base=base
            )
            base += path.stat().st_size
        removed = await rotate_remote(rc, site, int(remote.get("backup_keep") or 14))
    _mark(site, remote["name"], [backup.id], removed)
    log.info("cloud.backup_uploaded", site=site, id=backup.id, remote=remote["name"])
    return removed


async def upload_to_remotes(
    site: str, backup: BackupSet, progress: Progress | None = None
) -> dict[str, str | None]:
    """Upload *backup* to every backup remote; ``{remote: error or None}``.

    A failing remote doesn't stop the others nor fail the backup: it is
    recorded on the remote (status, ErrorLog, a notification). Call with
    the site's session bound and no transaction open.
    """
    session = grunt.get_session()
    remotes = await backup_remotes()
    await session.commit()  # no write lock held through the uploads
    outcome: dict[str, str | None] = {}
    for remote in remotes:
        if progress is not None:
            progress.set(
                stage=_("Uploading to “%(name)s”") % {"name": remote["title"] or remote["name"]},
                done=0,
                total=backup.size(),
            )
        try:
            await upload_backup(site, backup, remote, progress)
        except RemoteError as exc:
            outcome[remote["name"]] = str(exc)
            await record_status(remote, exc)
            continue
        outcome[remote["name"]] = None
        await record_status(
            remote, None, last_backup_at=datetime.now(UTC), last_backup_id=backup.id
        )
    return outcome


# Fetching back


def _part(path: Path) -> Path:
    return path.with_name(f".{path.name}.part")


async def fetch_backup(
    site: str, remote: dict[str, Any], backup_id: str, progress: Progress | None = None
) -> BackupSet:
    """Download the set *backup_id* from *remote* into ``backups/``.

    Files are written as hidden ``.part`` and renamed only when the whole set
    is down, like a freshly made set.
    """
    if get_backup(site, backup_id) is not None:
        raise RemoteError(_("Backup %(id)s is already on the server") % {"id": backup_id})
    out = backups_dir(site)
    async with Rclone(remote) as rc:
        kinds = _group(await rc.list(remote_dir(site))).get(backup_id)
        if not kinds:
            raise RemoteError(_("Backup %(id)s not found in the storage") % {"id": backup_id})
        entries = sorted(kinds.values(), key=lambda e: int(e.get("Size") or 0))
        if progress is not None:
            progress.set(total=sum(int(e.get("Size") or 0) for e in entries))
        done: list[Path] = []
        base = 0
        try:
            for entry in entries:
                dest = out / entry["Path"]
                done.append(dest)
                await rc.get_file(
                    f"{remote_dir(site)}/{entry['Path']}",
                    _part(dest),
                    progress=progress,
                    progress_base=base,
                )
                base += int(entry.get("Size") or 0)
            for dest in done:
                os.chmod(_part(dest), 0o600)
                _part(dest).rename(dest)
        except BaseException:
            for dest in done:
                _part(dest).unlink(missing_ok=True)
            raise
    _mark(site, remote["name"], [backup_id], [])
    backup = get_backup(site, backup_id)
    assert backup is not None
    log.info("cloud.backup_fetched", site=site, id=backup_id, remote=remote["name"])
    return backup
