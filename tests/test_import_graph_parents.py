"""``grunt.utils.import_graph``: an import is also an edge to the packages it runs."""

from pathlib import Path

from grunt.utils.import_graph import build


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_import_runs_every_package_above_the_module(tmp_path):
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a/__init__.py": "",
            "pkg/a/ns/b/__init__.py": "",  # pkg.a.ns: namespace package, no __init__
            "pkg/a/ns/b/mod.py": "",
            "pkg/c/__init__.py": "",
            "pkg/c/user.py": "from pkg.a.ns.b.mod import x\n",
        },
    )
    edges = build(tmp_path, "pkg").edges["pkg.c.user"]
    assert set(edges) == {"pkg.a.ns.b.mod", "pkg.a.ns.b", "pkg.a"}


def test_importer_own_packages_are_not_edges(tmp_path):
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a/__init__.py": "",
            "pkg/a/one.py": "from pkg.a.two import y\n",
            "pkg/a/two.py": "",
        },
    )
    graph = build(tmp_path, "pkg")
    assert set(graph.edges["pkg.a.one"]) == {"pkg.a.two"}
    assert graph.cyclic_modules() == set()
