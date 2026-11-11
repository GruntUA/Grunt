"""The core's import graph only loses cycles (IMPORT_CYCLES_PLAN.md).

``import_cycles_baseline.txt`` lists the modules that still sit in an import
cycle. A module outside the list must not join one; a module that left every
cycle must leave the list too, so the baseline only shrinks. The goal is an
empty file.

Every import statement counts, function-local, ``TYPE_CHECKING`` and ``lazy``
ones included, and so do the packages an import runs on the way
(``a.b.c`` runs ``a/__init__`` and ``a/b/__init__``) - see
:mod:`grunt.utils.import_graph`.
"""

from collections import deque
from pathlib import Path

from grunt.utils.import_graph import ImportGraph, build

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).with_name("import_cycles_baseline.txt")
SKIP = ("/tests/", "/migrations/versions/")


def _baseline() -> set[str]:
    lines = BASELINE.read_text(encoding="utf-8").splitlines()
    return {s for line in lines if (s := line.strip()) and not s.startswith("#")}


def _shortest_cycle(graph: ImportGraph, start: str) -> list[str]:
    """start -> ... -> start, fewest hops."""
    prev: dict[str, str] = {}
    queue = deque([start])
    while queue:
        v = queue.popleft()
        for w in graph.edges.get(v, {}):
            if w == start:
                path = [v]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return [start, *reversed(path[:-1]), start]
            if w not in prev:
                prev[w] = v
                queue.append(w)
    return [start]


def _describe(graph: ImportGraph, cycle: list[str]) -> str:
    hops = zip(cycle, cycle[1:], strict=False)
    return "\n".join(f"    {a} -> {b}  (line {graph.edges[a][b][0]})" for a, b in hops)


def test_no_new_module_joins_an_import_cycle():
    graph = build(ROOT, "grunt", skip=SKIP)
    new = sorted(graph.cyclic_modules() - _baseline())
    assert not new, "These modules are now part of an import cycle:\n" + "\n".join(
        f"  {m}\n{_describe(graph, _shortest_cycle(graph, m))}" for m in new
    )


def test_baseline_lists_only_modules_still_in_a_cycle():
    graph = build(ROOT, "grunt", skip=SKIP)
    gone = sorted(_baseline() - graph.cyclic_modules())
    assert not gone, f"No longer in any import cycle - remove from {BASELINE.name}:\n" + "\n".join(
        f"  {m}" for m in gone
    )
