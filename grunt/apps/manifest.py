"""App manifest - ``[project]`` and ``[tool.grunt]`` of the app's ``pyproject.toml``.

The standard ``[project]`` table holds what Python tooling knows anyway
(name, description, authors); ``[tool.grunt]`` adds what only Grunt needs::

    [project]
    name = "esign"
    description = "..."
    authors = [{ name = "Maxim S", email = "maks4a@gmail.com" }]

    [tool.grunt]
    title = "Електронний підпис"
    depends_on = ["hrm", { name = "cms", url = "https://github.com/GruntUA/cms.git" }]
    required_grunt = ">=0.5"
    modules = ["esign"]  # default: [<app dir name>]

A directory is a Grunt app when its pyproject.toml has ``[tool.grunt]``.
The version is not here - it comes from git tags (:mod:`grunt.version`).
"""

import tomllib
from pathlib import Path
from typing import Any

PYPROJECT = "pyproject.toml"


def _pyproject(app_dir: Path) -> dict[str, Any]:
    try:
        return tomllib.loads((app_dir / PYPROJECT).read_text())
    except OSError, tomllib.TOMLDecodeError:
        return {}


def is_app(app_dir: Path) -> bool:
    """Whether ``app_dir`` holds a Grunt app (its pyproject.toml has ``[tool.grunt]``)."""
    return "grunt" in _pyproject(app_dir).get("tool", {})


def read_manifest(app_dir: Path) -> dict[str, Any]:
    """The app's manifest with defaults filled in; empty values for a missing file.

    Keys: name, title, description, author, email, modules, depends_on, required_grunt.
    """
    data = _pyproject(app_dir)
    project = data.get("project", {})
    tool = data.get("tool", {}).get("grunt", {})
    author = (project.get("authors") or [{}])[0]
    name = project.get("name") or app_dir.name
    return {
        "name": name,
        "title": tool.get("title") or name,
        "description": project.get("description") or "",
        "author": author.get("name", ""),
        "email": author.get("email", ""),
        "modules": tool.get("modules") or [app_dir.name],
        "depends_on": tool.get("depends_on") or [],
        "required_grunt": tool.get("required_grunt") or "",
    }
