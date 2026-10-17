"""Versions of the framework and apps, taken from git tags.

A release is an annotated tag ``vX.Y.Z`` (``grunt release``). Between tags the
version is the next patch as a dev release, the way hatch-vcs builds the
package metadata: ``v0.4.2`` + 3 commits -> ``0.4.3.dev3+gabc1234``, with
``.dYYYYMMDD`` added when the working tree has uncommitted changes.

Without a tag (or without git, e.g. an unpacked archive) the framework falls
back to its installed package metadata and an app to ``version`` in its
``app.json``.
"""

import importlib.metadata
import json
import re
import subprocess
from datetime import date
from functools import cache
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

FRAMEWORK_DIR = Path(__file__).resolve().parent.parent  # apps/grunt

TAG_PATTERN = "v[0-9]*"
_DESCRIBE = re.compile(r"^v(?P<tag>.+)-(?P<distance>\d+)-g(?P<node>[0-9a-f]+)(?P<dirty>-dirty)?$")


def git_version(repo: Path) -> str | None:
    """Version of the checkout at ``repo`` from its latest ``v*`` tag, or None."""
    if not (repo / ".git").exists():
        return None
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "describe",
                "--tags",
                "--long",
                "--dirty",
                "--abbrev=7",
                "--match",
                TAG_PATTERN,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except OSError, subprocess.SubprocessError:
        return None
    m = _DESCRIBE.match(out)
    if not m:
        return None
    try:
        tag = Version(m["tag"])
    except InvalidVersion:
        return None
    distance, dirty = int(m["distance"]), bool(m["dirty"])
    if not distance and not dirty:
        return str(tag)
    major, minor, patch = (*tag.release, 0, 0)[:3]
    local = f"g{m['node']}" + (f".d{date.today():%Y%m%d}" if dirty else "")
    return f"{major}.{minor}.{patch + 1}.dev{distance}+{local}"


@cache
def framework_version() -> str:
    """Version of the running framework (``grunt.__version__``)."""
    found = git_version(FRAMEWORK_DIR)
    if found:
        return found
    try:
        return importlib.metadata.version("grunt")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


def _app_json(app_dir: Path) -> dict:
    try:
        return json.loads((app_dir / "app.json").read_text())
    except OSError, ValueError:
        return {}


@cache
def app_version(app_dir: Path, default: str | None = None) -> str:
    """Version of the app at ``apps/<name>``: its own git tags, else ``default``
    or the app.json version."""
    if app_dir.resolve() == FRAMEWORK_DIR:
        return framework_version()
    return git_version(app_dir) or default or str(_app_json(app_dir).get("version") or "0.0.0")


def required_framework(app_dir: Path) -> str:
    """The ``required_grunt`` specifier from the app's app.json (``""`` = any)."""
    return str(_app_json(app_dir).get("required_grunt") or "")


def compatibility_error(app_dir: Path) -> str | None:
    """Why the app cannot run on this framework version, or None when it can.

    Dev releases count (``0.5.1.dev3`` satisfies ``>=0.5``); a malformed
    specifier is reported rather than silently ignored.
    """
    spec = required_framework(app_dir)
    if not spec:
        return None
    try:
        allowed = SpecifierSet(spec)
    except InvalidSpecifier:
        return f"invalid required_grunt {spec!r}"
    current = framework_version()
    if allowed.contains(current, prereleases=True):
        return None
    return f"needs grunt {spec}, running {current}"
