"""Pick the tests affected by uncommitted changes (``grunt test --changed``).

The full suite runs in CI; locally only what the change can break:

* a changed test file runs itself;
* a changed module (``grunt/auth/login.py``) runs the tests that name it
  (``grunt.auth.login``, ``from grunt.auth import login``, ``patch("grunt.auth.login.x")``),
  the tests in its package's ``tests/`` folder and ``test_*login*.py`` files;
* a changed DocType file (``doctypes/ToDo/todo.json``) runs the tests that
  mention ``"ToDo"`` and the DocType's own ``tests/``;
* a change to the test harness (``conftest.py``, ``tests/support.py``,
  ``pyproject.toml``) needs the full suite.

Frontend files are handed to ``vitest related``, which follows imports itself.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FRONTEND_SUFFIXES = (".ts", ".vue", ".js", ".mjs")
HARNESS_FILES = {"conftest.py", "pyproject.toml", "support.py"}
# Too common to say anything about which tests cover them.
GENERIC_STEMS = {"__init__", "base", "utils", "service", "models", "types", "main", "api", "hooks"}
SKIP_DIRS = {".venv", "node_modules", ".git", "dist", "__pycache__"}


@dataclass
class Selection:
    tests: set[Path] = field(default_factory=set)
    frontend: list[Path] = field(default_factory=list)
    python: list[Path] = field(default_factory=list)  # changed .py files, for ruff
    uncovered: list[Path] = field(default_factory=list)  # changed sources no test names
    full: str | None = None  # why the whole suite is needed, if it is


def changed_files(repo: Path, base: str = "HEAD") -> list[Path]:
    """Files changed against ``base`` (committed, staged or not) plus untracked
    ones; deleted files are left out."""

    def git(*args: str) -> list[str]:
        out = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
        ).stdout
        return [line for line in out.splitlines() if line]

    names = git("diff", "--name-only", base) + git("ls-files", "--others", "--exclude-standard")
    return sorted({repo / n for n in names if (repo / n).is_file()})


def _is_test_file(path: Path) -> bool:
    return path.suffix == ".py" and path.name.startswith("test_")


def _test_files(repo: Path) -> list[Path]:
    return sorted(
        p for p in repo.rglob("test_*.py") if not SKIP_DIRS.intersection(p.relative_to(repo).parts)
    )


def _module_patterns(module: str, package: bool) -> list[re.Pattern[str]]:
    """How a test refers to ``module``. A package (``__init__.py``) matches only
    itself, not ``package.submodule``; the top-level package matches nothing -
    every test imports it."""
    parent, _, leaf = module.rpartition(".")
    if not parent:
        return []
    tail = r"(?![\w.])" if package else r"\b"
    return [
        re.compile(rf"\b{re.escape(module)}{tail}"),
        re.compile(rf"\bfrom {re.escape(parent)} import [^\n]*\b{re.escape(leaf)}\b"),
    ]


def _doctype_dir(path: Path) -> Path | None:
    parts = path.parts
    if "doctypes" in parts[:-1]:
        i = parts.index("doctypes")
        if i + 1 < len(parts) - 1:
            return Path(*parts[: i + 2])
    return None


def select(repo: Path, changed: list[Path]) -> Selection:
    sel = Selection()
    tests = _test_files(repo)
    texts: dict[Path, str] = {}

    def text(test: Path) -> str:
        if test not in texts:
            texts[test] = test.read_text(errors="ignore")
        return texts[test]

    for path in changed:
        rel = path.relative_to(repo)
        if path.suffix in FRONTEND_SUFFIXES and rel.parts[0] == "frontend":
            sel.frontend.append(path)
            continue
        if path.suffix == ".py":
            sel.python.append(path)
        if path.name in HARNESS_FILES and (path.parent == repo or "tests" in rel.parts):
            sel.full = sel.full or str(rel)
            continue
        if _is_test_file(path):
            sel.tests.add(path)
            continue

        found: set[Path] = set()
        dt_dir = _doctype_dir(rel)
        if dt_dir is not None:
            name = dt_dir.name
            needle = re.compile(rf"[\"']{re.escape(name)}[\"']")
            found |= {t for t in tests if needle.search(text(t))}
            found |= {t for t in tests if (repo / dt_dir) in t.parents}
        if path.suffix == ".py":
            parts = rel.with_suffix("").parts
            package = parts[-1] == "__init__"
            patterns = _module_patterns(".".join(parts[:-1] if package else parts), package)
            found |= {t for t in tests if any(p.search(text(t)) for p in patterns)}
            # Tests kept next to the code: <package>/tests/.
            found |= {t for t in tests if path.parent / "tests" in t.parents}
            stem = path.stem
            if stem not in GENERIC_STEMS and len(stem) > 3:
                found |= {t for t in tests if stem in t.stem}
        if found:
            sel.tests |= found
        elif path.suffix == ".py" or dt_dir is not None:
            sel.uncovered.append(path)
    return sel
