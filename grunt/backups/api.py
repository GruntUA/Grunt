"""HTTP side of backups: make one now, download a file by a short-lived signed link.

A backup file is fetched with a plain link (``<a href>`` can't send a bearer
token), so the list hands out URLs signed for DOWNLOAD_TTL_SECONDS; only a
System Manager ever sees them.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import FileResponse

from grunt import whitelist
from grunt.backups import _NAME, backups_dir
from grunt.config import settings
from grunt.i18n import _

DOWNLOAD_TTL_SECONDS = 15 * 60
_DOWNLOAD = "/api/v1/method/grunt.backups.api.download"


def _site() -> str:
    from grunt.site.manager import site_manager

    return site_manager.get_active_site()


def _signature(site: str, name: str, exp: int) -> str:
    msg = f"backup:{site}:{name}:{exp}".encode()
    return hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()


def download_url(site: str, name: str, now: float | None = None) -> str:
    exp = int((time.time() if now is None else now) + DOWNLOAD_TTL_SECONDS)
    query = urlencode({"file": name, "exp": exp, "sig": _signature(site, name, exp)})
    return f"{_DOWNLOAD}?{query}"


@whitelist(allow_guest=True)
async def download(file: str, exp: int, sig: str) -> FileResponse:
    """A backup file, for a valid unexpired signature (see :func:`download_url`)."""
    site = _site()
    if exp < time.time() or not hmac.compare_digest(sig, _signature(site, file, exp)):
        raise HTTPException(status_code=403, detail=_("The link is invalid or expired"))
    path = backups_dir(site) / file
    if not _NAME.match(file) or not path.is_file():
        raise HTTPException(status_code=404, detail=_("Backup file not found"))
    return FileResponse(path, filename=file, media_type="application/octet-stream")


@whitelist(roles=["System Manager"])
async def backup_now(
    with_database: bool = True, with_files: bool = True, with_config: bool = True
) -> dict:
    """Queue a backup of the chosen parts (the worker makes it; it shows up in the list)."""
    from grunt.backups.tasks import backup_now as task

    if not (with_database or with_files or with_config):
        raise HTTPException(status_code=400, detail=_("Choose at least one part to back up"))
    await task.kiq(with_database=with_database, with_files=with_files, with_config=with_config)
    return {"queued": True}
