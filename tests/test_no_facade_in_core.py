"""The core does not import the ``grunt`` facade (IMPORT_CYCLES_PLAN.md, step 9).

``grunt/__init__`` binds the developer API from ``grunt.app`` - built on top of
the whole core. A core module importing it closes a cycle through everything,
so the core imports what it needs from the module that defines it.

Allowed: the facade itself (``grunt/__init__``, ``grunt/app``) and the tools
that hand the facade to app code on purpose - ``testkit`` (app test fixtures)
and ``utils/shell`` (``grunt shell``).
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "grunt"
ALLOWED = {"__init__.py", "testkit.py", "utils/shell.py"}
ALLOWED_DIRS = ("app/", "tests/", "migrations/versions/")


def _facade_imports(path: Path) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        plain = isinstance(node, ast.Import) and any(a.name == "grunt" for a in node.names)
        named = isinstance(node, ast.ImportFrom) and node.module == "grunt" and node.level == 0
        if plain or named:
            lines.append(node.lineno)
    return lines


def test_core_modules_do_not_import_the_facade():
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED or any(f"/{d}" in f"/{rel}" for d in ALLOWED_DIRS):
            continue
        found += [f"grunt/{rel}:{line}" for line in _facade_imports(path)]
    assert not found, "Import from the defining module, not the grunt facade:\n" + "\n".join(found)
