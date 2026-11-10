"""Import graph of a Python package, read from source with :mod:`ast`.

Used by ``tests/test_import_cycles.py`` to keep the core free of import cycles
(IMPORT_CYCLES_PLAN.md). Nothing is imported or executed.

Every ``import`` / ``from … import`` statement is an edge, wherever it stands:
module level, inside a function, under ``if TYPE_CHECKING:``, or ``lazy``.
A function-local import still makes the two modules depend on each other, and
CodeQL counts it too (``py/cyclic-import``).

``from pkg import name`` is an edge to ``pkg.name`` when that is a module, else
to ``pkg`` itself - the package's ``__init__`` runs, so it is a dependency.
"""

import ast
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportGraph:
    """Modules of one package and the imports between them."""

    modules: dict[str, Path]
    # importer -> imported -> line numbers of the import statements
    edges: dict[str, dict[str, list[int]]] = field(default_factory=dict)

    def cycles(self) -> list[list[str]]:
        """Strongly connected components with more than one module, largest first."""
        return sorted(
            (sorted(c) for c in _strongly_connected(self.modules, self.edges) if len(c) > 1),
            key=len,
            reverse=True,
        )

    def cyclic_modules(self) -> set[str]:
        return {m for comp in self.cycles() for m in comp}

    def edges_within(self, comp: Iterable[str]) -> list[tuple[str, str, list[int]]]:
        members = set(comp)
        return [
            (a, b, lines)
            for a in sorted(members)
            for b, lines in sorted(self.edges.get(a, {}).items())
            if b in members
        ]


def build(root: Path, package: str, *, skip: Iterable[str] = ()) -> ImportGraph:
    """Read every ``*.py`` under ``root / package``.

    ``skip``: path fragments (posix, relative to ``root``) whose files are left out,
    e.g. ``"/tests/"`` or ``"/migrations/versions/"``.
    """
    skip = tuple(skip)
    modules: dict[str, Path] = {}
    for path in sorted((root / package).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if any(s in f"/{rel}" for s in skip):
            continue
        parts = list(path.relative_to(root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules[".".join(parts)] = path

    def resolve(name: str) -> str | None:
        while name and name not in modules:
            name = name.rpartition(".")[0]
        return name or None

    edges: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for mod, path in modules.items():
        is_package = path.name == "__init__.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    anchor = mod.split(".") if is_package else mod.split(".")[:-1]
                    anchor = anchor[: len(anchor) - (node.level - 1)]
                    base = ".".join([*anchor, base] if base else anchor)
                targets = [
                    f"{base}.{alias.name}" if f"{base}.{alias.name}" in modules else base
                    for alias in node.names
                ]
            else:
                continue
            for target in targets:
                if target != package and not target.startswith(f"{package}."):
                    continue
                dep = resolve(target)
                if dep and dep != mod:
                    edges[mod][dep].append(node.lineno)

    return ImportGraph(modules, {a: dict(b) for a, b in edges.items()})


def _strongly_connected(nodes: Iterable[str], edges: dict[str, dict[str, list[int]]]):
    """Tarjan's algorithm, iterative (the core is deeper than the recursion limit likes)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    counter = 0
    for start in nodes:
        if start in index:
            continue
        work = [(start, iter(edges.get(start, {})))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            v, children = work[-1]
            for w in children:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(edges.get(w, {}))))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    yield comp
