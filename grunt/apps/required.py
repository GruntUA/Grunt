"""Apps an app needs - ``depends_on`` in its ``app.json``.

An entry is an app name or ``{"name": ..., "url": ...}``, the git repository
to clone it from when the bench doesn't have it yet (like ``required_apps`` in
Frappe)::

    "depends_on": ["hrm", {"name": "cms", "url": "https://github.com/GruntUA/cms.git"}]

A site never runs an app without its dependencies: ``sync_installed_apps``
(``grunt migrate`` / ``app install`` / ``site create``) adds the missing ones
to ``installed_apps`` ahead of the app that needs them, and ``grunt update``
clones the ones the bench lacks.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from pathlib import Path

CORE_APP = "grunt"


class Dependency(NamedTuple):
    name: str
    url: str | None = None


class MissingAppError(Exception):
    def __init__(self, dep: Dependency, needed_by: str) -> None:
        self.dep = dep
        self.needed_by = needed_by
        how = f"git clone {dep.url} apps/{dep.name}" if dep.url else f"put it into apps/{dep.name}"
        super().__init__(f"App '{needed_by}' needs '{dep.name}', which is not in the bench: {how}")


class DependencyCycleError(Exception):
    pass


def dependencies(app_dir: Path) -> list[Dependency]:
    """The app's ``depends_on``, both entry forms as :class:`Dependency`."""
    try:
        meta = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    deps = []
    for entry in meta.get("depends_on") or []:
        if isinstance(entry, str):
            deps.append(Dependency(entry))
        else:
            deps.append(Dependency(entry["name"], entry.get("url")))
    return [d for d in deps if d.name != CORE_APP]


def with_dependencies(apps_dir: Path, installed: list[str]) -> list[str]:
    """*installed* plus the apps they depend on, each dependency before its first user.

    The order of *installed* is otherwise kept. An installed app missing from
    the bench is left as is (its sync skips it); a missing dependency raises
    :class:`MissingAppError`.
    """
    result: list[str] = []
    visiting: list[str] = []

    def visit(name: str) -> None:
        if name in result:
            return
        if name in visiting:
            cycle = " -> ".join([*visiting[visiting.index(name) :], name])
            raise DependencyCycleError(f"Circular depends_on: {cycle}")
        visiting.append(name)
        for dep in dependencies(apps_dir / name):
            if not (apps_dir / dep.name).is_dir():
                raise MissingAppError(dep, name)
            visit(dep.name)
        visiting.pop()
        result.append(name)

    for name in installed:
        visit(name)
    return result


def ensure_site_dependencies(site_file: Path, apps_dir: Path) -> list[str]:
    """Add the missing dependencies of the site's apps to its ``installed_apps``.

    Returns the added app names; ``grunt.site`` is rewritten only if any.
    """
    config = json.loads(site_file.read_text(encoding="utf-8"))
    installed = config.get("installed_apps", [])
    resolved = with_dependencies(apps_dir, installed)
    added = [name for name in resolved if name not in installed]
    if added:
        config["installed_apps"] = resolved
        site_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def clone_missing(apps_dir: Path, names: list[str] | None = None) -> list[str]:
    """Clone the dependencies the bench lacks, transitively, from their ``url``.

    *names* limits the walk to those apps (default: every app in the bench).
    Dependencies without a ``url`` are left to :func:`with_dependencies` to
    report. Returns the cloned app names.
    """
    queue = names or sorted(d.name for d in apps_dir.iterdir() if d.is_dir())
    seen: set[str] = set()
    cloned: list[str] = []
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        for dep in dependencies(apps_dir / name):
            target = apps_dir / dep.name
            if not target.exists() and dep.url:
                subprocess.run(["git", "clone", dep.url, str(target)], check=True)
                cloned.append(dep.name)
            queue.append(dep.name)
    return cloned
