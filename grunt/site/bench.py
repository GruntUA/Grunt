"""Where the bench is - the directory holding ``apps/`` and ``sites/``.

A leaf: :mod:`grunt.i18n` reads the apps' catalogs from here and
:class:`grunt.site.manager.SiteManager` the sites, neither importing the other.
Found once, on first use; ``SiteManager.bench_dir`` reads and sets it.
"""

from pathlib import Path

from grunt.log import log

_bench_dir: Path | None = None


def find_bench_dir(start: Path) -> Path | None:
    """Walk up from *start* looking for a directory that has both apps/ and sites/."""
    check = start if start.is_dir() else start.parent
    for _ in range(8):
        if (check / "apps").is_dir() and (check / "sites").is_dir():
            return check.resolve()
        if check == check.parent:
            break
        check = check.parent
    return None


def _discover() -> Path:
    # Up from cwd first, then from where the package is installed.
    found = find_bench_dir(Path.cwd()) or find_bench_dir(Path(__file__).resolve())
    if found is not None:
        return found
    # No ancestor of cwd or of this file has both apps/ and sites/ - guess two
    # levels up from cwd (matches apps/<app>/ as cwd, the common case when
    # running a bench command from an app dir).
    guessed = Path.cwd().parent.parent.resolve()
    log.warning("site_manager.bench_dir_guessed", cwd=str(Path.cwd()), guessed=str(guessed))
    return guessed


def bench_dir() -> Path:
    """The bench directory (found on first call)."""
    global _bench_dir
    if _bench_dir is None:
        _bench_dir = _discover()
    return _bench_dir


def set_bench_dir(path: Path) -> None:
    """Point the process at another bench (tests, tooling)."""
    global _bench_dir
    _bench_dir = path.resolve()
