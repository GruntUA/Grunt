"""The clouds a ``StorageRemote`` can point at, and how each becomes an rclone section.

``StorageRemote.provider`` is one of :data:`PROVIDERS`; its builder turns the
row into rclone backend options. ``Other`` takes the rclone backend type and
its options as typed - any of rclone's ~70 backends works that way.
``rclone_options`` (``key = value`` lines) is appended for every provider and
wins over the generated values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from grunt import _

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class OAuthEndpoints:
    authorize_url: str
    token_url: str
    scope: str = ""
    extra_params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Provider:
    name: str  # StorageRemote.provider value
    rclone_type: str
    build: Callable[[dict[str, Any]], dict[str, Any]]
    oauth: OAuthEndpoints | None = None
    # rclone's command to get a token with its own client id, for pasting
    authorize_command: str = ""


def _secret(remote: dict[str, Any], fieldname: str) -> str:
    from grunt.storage.cloud.rclone import obscure

    value = remote.get(fieldname) or ""
    return obscure(value) if value else ""


def _oauth(remote: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_id": remote.get("client_id") or "",
        "client_secret": remote.get("client_secret") or "",
        "token": remote.get("oauth_token") or "",
    }


def _drive(remote: dict[str, Any]) -> dict[str, Any]:
    # drive.file: only what this app created - no access to the rest of the
    # Drive, and Google needs no app verification for it.
    return {"type": "drive", "scope": "drive.file", **_oauth(remote)}


def _dropbox(remote: dict[str, Any]) -> dict[str, Any]:
    return {"type": "dropbox", **_oauth(remote)}


def _onedrive(remote: dict[str, Any]) -> dict[str, Any]:
    extra = remote.get("oauth_extra") or {}
    if isinstance(extra, str):
        import json

        try:
            extra = json.loads(extra)
        except ValueError:
            extra = {}
    return {
        "type": "onedrive",
        **_oauth(remote),
        "drive_id": extra.get("drive_id", ""),
        "drive_type": extra.get("drive_type", ""),
    }


def _mega(remote: dict[str, Any]) -> dict[str, Any]:
    return {"type": "mega", "user": remote.get("username"), "pass": _secret(remote, "password")}


def _s3(remote: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "s3",
        "provider": remote.get("s3_provider") or "Other",
        "env_auth": "false",
        "access_key_id": remote.get("access_key_id"),
        "secret_access_key": remote.get("secret_access_key"),
        "region": remote.get("region"),
        "endpoint": remote.get("endpoint"),
    }


def _webdav(remote: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "webdav",
        "url": remote.get("endpoint"),
        "vendor": remote.get("webdav_vendor") or "other",
        "user": remote.get("username"),
        "pass": _secret(remote, "password"),
    }


def _sftp(remote: dict[str, Any]) -> dict[str, Any]:
    key = (remote.get("ssh_private_key") or "").strip()
    return {
        "type": "sftp",
        "host": remote.get("host"),
        "port": remote.get("port") or "",
        "user": remote.get("username"),
        "pass": _secret(remote, "password"),
        # rclone wants the PEM on one line with literal \n
        "key_pem": key.replace("\r\n", "\n").replace("\n", "\\n") if key else "",
    }


def _smb(remote: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "smb",
        "host": remote.get("host"),
        "port": remote.get("port") or "",
        "user": remote.get("username"),
        "pass": _secret(remote, "password"),
        "domain": remote.get("domain"),
    }


def _local(remote: dict[str, Any]) -> dict[str, Any]:
    return {"type": "local"}


def _other(remote: dict[str, Any]) -> dict[str, Any]:
    if not remote.get("rclone_type"):
        from grunt.storage.cloud.rclone import RemoteError

        raise RemoteError(_("Enter the rclone backend type"))
    return {"type": remote["rclone_type"], **_oauth(remote)}


_GOOGLE = OAuthEndpoints(
    "https://accounts.google.com/o/oauth2/auth",
    "https://oauth2.googleapis.com/token",
    "https://www.googleapis.com/auth/drive.file",
    {"access_type": "offline", "prompt": "consent"},
)
_DROPBOX = OAuthEndpoints(
    "https://www.dropbox.com/oauth2/authorize",
    "https://api.dropboxapi.com/oauth2/token",
    "",
    {"token_access_type": "offline"},
)
_MICROSOFT = OAuthEndpoints(
    "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "Files.ReadWrite Files.ReadWrite.All offline_access User.Read",
)

PROVIDERS: dict[str, Provider] = {
    p.name: p
    for p in (
        Provider("Google Drive", "drive", _drive, _GOOGLE, 'rclone authorize "drive"'),
        Provider("Dropbox", "dropbox", _dropbox, _DROPBOX, 'rclone authorize "dropbox"'),
        Provider("OneDrive", "onedrive", _onedrive, _MICROSOFT, 'rclone authorize "onedrive"'),
        Provider("MEGA", "mega", _mega),
        Provider("S3", "s3", _s3),
        Provider("WebDAV", "webdav", _webdav),
        Provider("SFTP", "sftp", _sftp),
        Provider("SMB", "smb", _smb),
        Provider("Server folder", "local", _local),
        Provider("Other", "", _other),
    )
}


def get_provider(name: str | None) -> Provider:
    provider = PROVIDERS.get(name or "")
    if provider is None:
        from grunt.storage.cloud.rclone import RemoteError

        raise RemoteError(_("Unknown storage type: %(name)s") % {"name": name})
    return provider


def parse_options(text: str | None) -> dict[str, str]:
    """``key = value`` lines (``#`` comments, blanks skipped)."""
    options: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        options[key.strip()] = value.strip()
    return options


def provider_section(remote: dict[str, Any]) -> dict[str, Any]:
    """rclone options of the provider section for *remote*."""
    section = get_provider(remote.get("provider")).build(remote)
    section.update(parse_options(remote.get("rclone_options")))
    return section
