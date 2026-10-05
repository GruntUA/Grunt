"""Internal helpers for GruntApp."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def load_app_hook_module(
    app_dir: Path, app_name: str, hook_module: str = "install"
) -> ModuleType | None:
    """Import ``<app_dir>/<hook_module>.py`` if it exists, else return None.

    Shared by ``cli.app`` (``before_uninstall``) and ``startup.app_install``
    (``after_install``) - both need to run an optional lifecycle hook defined
    in an app's own ``install.py`` without that app being on ``sys.path`` as
    an importable package.
    """
    import importlib.util

    path = app_dir / f"{hook_module}.py"
    if not path.exists():
        return None

    spec = importlib.util.spec_from_file_location(f"{app_name}.{hook_module}", path)
    if not spec or not spec.loader:
        return None

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _collect_template_dirs() -> list[str]:
    """Return all Jinja2 template directories in priority order.

    Search order (first match wins in Jinja2 FileSystemLoader):
    1. ``bench_dir/apps/<app>/*/templates/`` - installed app templates
    2. ``grunt/<module>/templates/`` - framework module templates
    """
    from grunt.site.manager import site_manager

    dirs: list[str] = []

    # 1. Installed external apps
    ext_apps_dir = site_manager.bench_dir / "apps"
    if ext_apps_dir.is_dir():
        for pattern in ("*/templates", "*/*/templates"):
            for p in sorted(ext_apps_dir.glob(pattern)):
                if p.is_dir():
                    dirs.append(str(p))

    # 2. All grunt framework module template directories
    _grunt_root = Path(__file__).parent.parent
    for p in sorted(_grunt_root.rglob("templates")):
        if p.is_dir():
            dirs.append(str(p))

    return dirs
