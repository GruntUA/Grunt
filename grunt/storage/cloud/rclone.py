"""Running rclone against one ``StorageRemote``.

rclone (https://rclone.org, one binary) speaks every cloud we offer - Google
Drive, Dropbox, OneDrive, MEGA, S3, WebDAV/Nextcloud, SFTP, SMB - so the
framework never carries a client library per provider. Each call writes a
throw-away config (0600, in a private temp dir) built from the remote's row,
runs one command and reads the config back: rclone refreshes OAuth tokens
in place, and a new token must reach the database or the next call would
start from a stale one.

Paths are relative to the remote's root folder; with encryption on, the
remote is wrapped in rclone's ``crypt`` (file contents only - names stay
readable, so listings and rotation by name keep working).

Usage::

    async with Rclone(remote) as rc:
        await rc.put_file(local_path, "backups/site/x.zst", progress=progress)
        entries = await rc.list("backups/site")
"""

import asyncio
import base64
import configparser
import contextlib
import hashlib
import io
import json
import os
import platform
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import httpx2
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import grunt
from grunt import _, log
from grunt.config import settings
lazy from grunt.progress import Progress
lazy from grunt.storage.cloud.providers import provider_section

# rclone's fixed key for "obscured" config values (lib/obscure). Obscuring is
# not encryption - it only keeps secrets from being read over a shoulder -
# but rclone refuses plain passwords in these fields.
_OBSCURE_KEY = bytes.fromhex("9c935b48730a554d6bfd7c63c886a92bd390198eb8128afbf4de162b8b95f638")

# rclone exit codes (docs: "Exit Code")
EXIT_DIR_NOT_FOUND = 3
EXIT_FILE_NOT_FOUND = 4

BASE = "remote"  # section of the provider itself
CRYPT = "secret"  # section wrapping it when encryption is on


class RemoteError(RuntimeError):
    """An rclone call failed - the message is rclone's own last error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def obscure(value: str) -> str:
    """``rclone obscure``: AES-CTR with rclone's fixed key, random IV, base64url."""
    iv = os.urandom(16)
    encryptor = Cipher(algorithms.AES(_OBSCURE_KEY), modes.CTR(iv)).encryptor()
    data = iv + encryptor.update(value.encode()) + encryptor.finalize()
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


# Where rclone is put when the server has none: per user, shared by every site.
INSTALL_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "grunt/bin"
DOWNLOAD_URL = "https://downloads.rclone.org"
_OS = {"linux": "linux", "darwin": "osx", "freebsd": "freebsd"}
_ARCH = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv7l": "arm-v7",
}
_install_lock = asyncio.Lock()


def _find() -> str | None:
    found = shutil.which(settings.rclone_binary)
    if found:
        return found
    managed = INSTALL_DIR / "rclone"
    return str(managed) if os.access(managed, os.X_OK) else None


def binary() -> str:
    """Path of the rclone binary; RemoteError when it is not installed."""
    found = _find()
    if not found:
        raise RemoteError(_("rclone is not installed on the server (https://rclone.org/install/)"))
    return found


def is_installed() -> bool:
    return _find() is not None


async def ensure_installed() -> str:
    """Path of rclone, downloading the current release into INSTALL_DIR if there is none.

    The zip is checked against rclone's published SHA256SUMS before the binary
    is unpacked. RemoteError when the platform is not supported or the
    download fails.
    """
    if found := _find():
        return found
    async with _install_lock:
        if found := _find():
            return found
        return await _install()


async def _install() -> str:

    system = _OS.get(platform.system().lower())
    arch = _ARCH.get(platform.machine().lower())
    if not system or not arch:
        raise RemoteError(_("rclone is not installed on the server (https://rclone.org/install/)"))
    log.info("cloud.rclone_install", dir=str(INSTALL_DIR))
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=INSTALL_DIR) as tmp:
        try:
            async with httpx2.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                latest = await client.get(f"{DOWNLOAD_URL}/version.txt")
                version = latest.raise_for_status().text.split()[-1]  # "rclone v1.75.2"
                base = f"{DOWNLOAD_URL}/{version}"
                zip_name = f"rclone-{version}-{system}-{arch}.zip"
                archive = Path(tmp) / zip_name
                sums = (await client.get(f"{base}/SHA256SUMS")).raise_for_status().text
                digest = hashlib.sha256()
                async with client.stream("GET", f"{base}/{zip_name}") as response:
                    response.raise_for_status()
                    with archive.open("wb") as f:
                        async for chunk in response.aiter_bytes():
                            digest.update(chunk)
                            f.write(chunk)
        except httpx2.HTTPError as e:
            log.error("cloud.rclone_install_failed", error=str(e))
            raise RemoteError(_("Could not download rclone: {0}").format(e)) from e
        # SHA256SUMS is PGP-signed text: "<hash>  <file>" lines among the armor
        expected = next(
            (line.split()[0] for line in sums.splitlines() if line.split()[-1:] == [zip_name]),
            None,
        )
        if expected != digest.hexdigest():
            raise RemoteError(_("Could not download rclone: checksum mismatch"))

        def unpack() -> Path:
            with zipfile.ZipFile(archive) as z:
                member = next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == "rclone")
                target = Path(tmp) / "rclone"
                with z.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            target.chmod(0o755)
            return target

        target = await asyncio.to_thread(unpack)
        os.replace(target, INSTALL_DIR / "rclone")  # atomic: never a half-written binary
    log.info("cloud.rclone_installed", path=str(INSTALL_DIR / "rclone"))
    return str(INSTALL_DIR / "rclone")


class _Config(configparser.ConfigParser):
    """rclone option names are case-sensitive - keep them as written."""

    def optionxform(self, optionstr: str) -> str:
        return optionstr


def build_config(remote: dict[str, Any]) -> configparser.ConfigParser:
    """The rclone config of *remote* (a ``StorageRemote`` row with real secrets)."""

    config = _Config(interpolation=None)
    config[BASE] = {k: str(v) for k, v in provider_section(remote).items() if v not in (None, "")}
    if remote.get("encrypt"):
        if not remote.get("encryption_password"):
            raise RemoteError(_("Encryption is on, but no encryption password is set"))
        config[CRYPT] = {
            "type": "crypt",
            "remote": f"{BASE}:{root_folder(remote)}",
            "password": obscure(remote["encryption_password"]),
            "filename_encryption": "off",
            "directory_name_encryption": "false",
        }
        if remote.get("encryption_salt"):
            config[CRYPT]["password2"] = obscure(remote["encryption_salt"])
    return config


def root_folder(remote: dict[str, Any]) -> str:
    """The folder everything lives under; absolute for a server folder."""
    folder = (remote.get("root_folder") or "").strip().rstrip("/")
    return folder if remote.get("provider") == "Server folder" else folder.lstrip("/")


def config_text(remote: dict[str, Any]) -> str:
    """The config as rclone.conf text - to keep somewhere safe for disaster recovery."""

    out = io.StringIO()
    build_config(remote).write(out)
    return out.getvalue()


class Rclone:
    """One remote's config on disk for the duration of an ``async with``."""

    def __init__(self, remote: dict[str, Any]) -> None:
        self.remote = remote
        self._dir: Path | None = None
        self._token = remote.get("oauth_token") or ""

    async def __aenter__(self) -> Rclone:
        self._dir = Path(tempfile.mkdtemp(prefix="grunt-rclone-"))  # 0700
        conf = self.config_path
        conf.touch(mode=0o600)
        with conf.open("w") as f:
            build_config(self.remote).write(f)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._dir is None:
            return
        try:
            await self._save_refreshed_token()
        finally:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None

    @property
    def config_path(self) -> Path:
        assert self._dir is not None, "use Rclone inside `async with`"
        return self._dir / "rclone.conf"

    def target(self, path: str = "") -> str:
        """``section:path`` for *path* relative to the root folder."""
        path = path.strip("/")
        if self.remote.get("encrypt"):
            return f"{CRYPT}:{path}"
        root = root_folder(self.remote)
        return f"{BASE}:{'/'.join(p for p in (root, path) if p)}"

    async def _save_refreshed_token(self) -> None:
        """rclone rewrites ``token`` when it refreshes it - keep the new one."""
        config = _Config(interpolation=None)
        with contextlib.suppress(OSError, configparser.Error):
            config.read(self.config_path)
        token = config.get(BASE, "token", fallback="") if config.has_section(BASE) else ""
        name = self.remote.get("name")
        if not token or token == self._token or not name:
            return

        await grunt.db.set_value("StorageRemote", name, {"oauth_token": token})
        self._token = self.remote["oauth_token"] = token
        log.info("cloud.token_refreshed", remote=name)

    # Running

    async def run(
        self,
        *args: str,
        progress: Progress | None = None,
        progress_base: int = 0,
        stdin: bytes | None = None,
        ok_codes: Iterable[int] = (0,),
        stdout_to: Path | None = None,
    ) -> str:
        """Run ``rclone <args>``; return stdout. RemoteError on a failing exit code.

        *progress* follows rclone's transfer stats in bytes, offset by
        *progress_base* (several files of one job on one bar); *stdout_to*
        streams stdout into a file instead of memory (``cat`` of a big blob).
        A cancelled task (the progress raises) kills rclone.
        """
        cmd = [
            await ensure_installed(),
            "--config",
            str(self.config_path),
            "--use-json-log",
            "--log-level",
            "NOTICE",
            "--ask-password=false",
            "--low-level-retries",
            "5",
        ]
        if progress is not None:
            cmd += ["--stats", "2s", "--stats-log-level", "NOTICE"]
        cmd += list(args)

        def report(done: int) -> None:
            if progress is not None:
                progress.set(done=progress_base + done)

        out_file = stdout_to.open("wb") if stdout_to else None
        proc: asyncio.subprocess.Process | None = None
        errors: list[str] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=out_file or asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "RCLONE_CONFIG_PASS": ""},
            )
            stdout, _log = await asyncio.gather(
                self._feed_and_read(proc, stdin), self._read_log(proc, errors, report)
            )
            code = await proc.wait()
        except BaseException:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        finally:
            if out_file:
                out_file.close()
        if code not in tuple(ok_codes):
            message = (
                errors[-1] if errors else _("rclone exited with code %(code)s") % {"code": code}
            )
            log.warning(
                "cloud.rclone_failed",
                remote=self.remote.get("name"),
                cmd=args[0],
                code=code,
                error=message,
            )
            raise RemoteError(message, code)
        return stdout.decode() if stdout else ""

    @staticmethod
    async def _feed_and_read(proc: asyncio.subprocess.Process, stdin: bytes | None) -> bytes:
        if stdin is not None and proc.stdin is not None:
            proc.stdin.write(stdin)
            await proc.stdin.drain()
            proc.stdin.close()
        return await proc.stdout.read() if proc.stdout is not None else b""

    @staticmethod
    async def _read_log(
        proc: asyncio.subprocess.Process,
        errors: list[str],
        report: Callable[[int], None],
    ) -> None:
        assert proc.stderr is not None
        async for raw in proc.stderr:
            line = raw.decode(errors="replace").strip()
            try:
                entry = json.loads(line)
            except ValueError:
                if line:
                    errors.append(line)
                continue
            stats = entry.get("stats")
            if stats:
                report(stats.get("bytes") or 0)
            elif entry.get("level") in ("error", "critical", "fatal"):
                msg = str(entry.get("msg") or "").strip()
                obj = entry.get("object")
                errors.append(f"{obj}: {msg}" if obj else msg)

    # Operations - paths relative to the root folder

    async def put_file(
        self, local: Path, path: str, *, progress: Progress | None = None, progress_base: int = 0
    ) -> None:
        """Upload one file as *path* (rclone checks size/hash after the transfer)."""
        await self.run(
            "copyto", str(local), self.target(path), progress=progress, progress_base=progress_base
        )

    async def put_bytes(self, content: bytes, path: str) -> None:
        await self.run("rcat", self.target(path), stdin=content)

    async def get_file(
        self, path: str, local: Path, *, progress: Progress | None = None, progress_base: int = 0
    ) -> None:
        """Download *path* into the file *local*."""
        await self.run(
            "copyto", self.target(path), str(local), progress=progress, progress_base=progress_base
        )

    async def cat(self, path: str, *, offset: int = 0, count: int | None = None) -> bytes:
        """Bytes of *path* (a slice with *offset* / *count*)."""
        args = ["cat", self.target(path)]
        if offset:
            args += ["--offset", str(offset)]
        if count is not None:
            args += ["--count", str(count)]
        return await self._run_bytes(*args)

    async def _run_bytes(self, *args: str) -> bytes:
        assert self._dir is not None
        out = self._dir / "stdout"
        await self.run(*args, stdout_to=out)
        try:
            return out.read_bytes()
        finally:
            out.unlink(missing_ok=True)

    async def delete_file(self, path: str) -> None:
        await self.run("deletefile", self.target(path), ok_codes=(0, EXIT_FILE_NOT_FOUND))

    async def delete_files(self, paths: list[str], folder: str = "") -> None:
        """Delete many files under *folder* in one call."""
        if not paths:
            return
        assert self._dir is not None
        listing = self._dir / "delete.txt"
        listing.write_text("\n".join(paths) + "\n")
        await self.run(
            "delete",
            self.target(folder),
            "--files-from-raw",
            str(listing),
            "--no-traverse",
            ok_codes=(0, EXIT_DIR_NOT_FOUND),
        )

    async def copy_files(
        self, local_root: Path, paths: list[str], folder: str, *, progress: Progress | None = None
    ) -> None:
        """Upload *paths* (relative to *local_root*) under *folder*, keeping their layout."""
        if not paths:
            return
        assert self._dir is not None
        listing = self._dir / "copy.txt"
        listing.write_text("\n".join(paths) + "\n")
        await self.run(
            "copy",
            str(local_root),
            self.target(folder),
            "--files-from-raw",
            str(listing),
            "--no-traverse",
            progress=progress,
        )

    async def get_files(
        self, folder: str, paths: list[str], local_root: Path, *, progress: Progress | None = None
    ) -> None:
        """Download *paths* (relative to *folder*) into *local_root*, keeping their layout."""
        if not paths:
            return
        assert self._dir is not None
        listing = self._dir / "get.txt"
        listing.write_text("\n".join(paths) + "\n")
        await self.run(
            "copy",
            self.target(folder),
            str(local_root),
            "--files-from-raw",
            str(listing),
            "--no-traverse",
            progress=progress,
        )

    async def list(self, path: str = "", *, recursive: bool = False) -> list[dict[str, Any]]:
        """Files under *path* (``Path``, ``Size``, ``ModTime``); [] when it doesn't exist."""
        args = ["lsjson", self.target(path), "--files-only", "--no-mimetype"]
        if recursive:
            args.append("--recursive")
        try:
            out = await self.run(*args)
        except RemoteError as exc:
            if exc.code == EXIT_DIR_NOT_FOUND:  # stdout is a cut-off "[" then
                return []
            raise
        return json.loads(out) if out.strip() else []

    async def mkdir(self, path: str = "") -> None:
        await self.run("mkdir", self.target(path))

    async def about(self) -> dict[str, Any] | None:
        """Quota (``total``/``used``/``free`` bytes) - None where the provider has none."""
        try:
            out = await self.run("about", f"{BASE}:", "--json")
        except RemoteError:
            return None
        return json.loads(out) if out.strip() else None
