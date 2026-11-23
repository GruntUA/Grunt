"""Codemod: ``x["field"]`` / ``x.get("field")`` / ``doc.data["field"]`` -> ``x.field``.

Only where pyright proves the receiver is an :class:`~grunt.utils.attr_dict.AttrDict`
or a DocType controller - on a plain ``dict`` (or ``Any``) the attribute would
fail at run time, so those stay as they are. How the type is learnt: every
candidate receiver ``E`` is wrapped as ``reveal_type(E, expected_text="<id>")``
in place, pyright reports the real type in its mismatch message, the files are
restored, and only the confirmed sites are rewritten.

Left alone on purpose:

* a key that is not an identifier, starts with ``_``, or is a keyword;
* on an ``AttrDict`` - a key named like a ``dict`` attribute (``items``, ``get``...);
* on a controller - a key taken by a controller attribute (``user``, a method,
  a property...), except reading ``name``/``owner``/... (same value);
* ``del x["k"]``, a site inside ``try`` that catches ``KeyError`` (``x.k`` gives
  ``None`` instead of raising), a getter named like the key (``def name(self):
  return self.data.get("name")`` would recurse), and multi-line expressions;
* the attribute routing itself (``grunt/document/base.py``, ``document/mixins``).

Run it through ``grunt codemod attr-access``; then ``ruff format`` and the tests.
"""

from __future__ import annotations

import ast
import json
import keyword
import re
import subprocess
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = {"node_modules", ".venv", "dist", "uploads", "__pycache__", "migrations"}
_SKIP_FILES = ("grunt/document/base.py", "grunt/document/mixins/")
_DICT_ATTRS = frozenset(dir(dict))
# Controller properties that read the same value as the field of that name.
_READABLE_SYS = frozenset(
    {
        "name",
        "id",
        "owner",
        "idx",
        "created_at",
        "modified_at",
        "modified_by",
        "parent",
        "parentfield",
        "parenttype",
    }
)
_KEYERROR_CATCHERS = {"KeyError", "LookupError", "Exception", "BaseException"}
_MISMATCH = re.compile(r'expected "(__C\d+__)" but received "(.*)"')


@dataclass
class Candidate:
    """One rewritable site. *kind*: ``sub`` ``E["k"]``, ``get`` ``E.get("k")``,
    ``datasub`` ``E.data["k"]``, ``dataget`` ``E.data.get("k")``."""

    id: str
    kind: str
    key: str
    store: bool
    line: int  # 1-based; the whole node is on this line
    end: int  # byte offset of the node's end
    recv_col: int  # byte offsets of the receiver E
    recv_end: int


@dataclass
class Result:
    files: dict[Path, str] = field(default_factory=dict)  # rewritten sources
    rewrites: int = 0
    candidates: int = 0
    probed: int = 0
    kept: Counter[str] = field(default_factory=Counter)  # receiver type -> sites left alone


# Finding candidates


def _key(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        k = node.value
        if k.isidentifier() and not keyword.iskeyword(k) and not k.startswith("_"):
            return k
    return None


def _catches_keyerror(parents: list[ast.AST]) -> bool:
    for p in parents:
        if not isinstance(p, ast.Try):
            continue
        for handler in p.handlers:
            if handler.type is None:
                return True
            types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
            names = {getattr(t, "id", getattr(t, "attr", "")) for t in types}
            if names & _KEYERROR_CATCHERS:
                return True
    return False


def _in_getter_of(parents: list[ast.AST], key: str) -> bool:
    return any(
        isinstance(p, ast.FunctionDef | ast.AsyncFunctionDef) and p.name == key for p in parents
    )


def _match(node: ast.AST) -> tuple[str, ast.expr, str] | None:
    if isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Del):
        k = _key(node.slice)
        if k:
            v = node.value
            if isinstance(v, ast.Attribute) and v.attr == "data":
                return "datasub", v.value, k
            return "sub", v, k
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and len(node.args) == 1
        and not node.keywords
    ):
        k = _key(node.args[0])
        if k:
            v = node.func.value
            if isinstance(v, ast.Attribute) and v.attr == "data":
                return "dataget", v.value, k
            return "get", v, k
    return None


def find_candidates(source: str, start: int = 0) -> list[Candidate]:
    """The rewritable sites of *source*; ids count from *start*."""
    tree = ast.parse(source)
    out: list[Candidate] = []

    def visit(node: ast.AST, parents: list[ast.AST]) -> None:
        found = _match(node)
        if found:
            kind, recv, k = found
            if (
                node.lineno == node.end_lineno  # type: ignore[attr-defined]
                and recv.lineno == recv.end_lineno
                and not _catches_keyerror(parents)
                and not _in_getter_of(parents, k)
            ):
                out.append(
                    Candidate(
                        id=f"__C{start + len(out)}__",
                        kind=kind,
                        key=k,
                        store=isinstance(getattr(node, "ctx", None), ast.Store),
                        line=node.lineno,  # type: ignore[attr-defined]
                        end=node.end_col_offset or 0,  # type: ignore[attr-defined]
                        recv_col=recv.col_offset,
                        recv_end=recv.end_col_offset or 0,
                    )
                )
        for child in ast.iter_child_nodes(node):
            visit(child, [node, *parents])

    visit(tree, [])
    return out


def _edit(source: str, edits: list[tuple[int, int, int, str]]) -> str:
    """Apply ``(line, byte_start, byte_end, text)`` edits, right to left."""
    lines = source.splitlines(keepends=True)
    for ln, start, end, text in sorted(edits, reverse=True):
        raw = lines[ln - 1].encode()
        lines[ln - 1] = (raw[:start] + text.encode() + raw[end:]).decode()
    return "".join(lines)


def probe_source(source: str, candidates: list[Candidate]) -> str:
    """*source* with every receiver wrapped in ``reveal_type(E, expected_text=id)``."""
    edits: list[tuple[int, int, int, str]] = []
    for c in candidates:
        edits.append((c.line, c.recv_col, c.recv_col, "reveal_type("))
        edits.append((c.line, c.recv_end, c.recv_end, f', expected_text="{c.id}")'))
    return _edit(source, edits)


def rewrite_source(source: str, candidates: list[Candidate]) -> str:
    """*source* with each candidate turned into ``E.key``."""
    lines = source.splitlines(keepends=True)
    edits = []
    for c in candidates:
        tail = lines[c.line - 1].encode()[c.recv_end : c.end].decode()
        keep = re.match(r"[)\s]*", tail)
        edits.append((c.line, c.recv_end, c.end, f"{keep[0] if keep else ''}.{c.key}"))
    return _edit(source, edits)


# Deciding


@dataclass
class _Classes:
    """Class name -> (base names, attribute names) for the trees searched."""

    info: dict[str, tuple[list[str], set[str]]] = field(default_factory=dict)

    def add(self, source: str) -> None:
        for n in ast.walk(ast.parse(source)):
            if isinstance(n, ast.ClassDef):
                bases = [getattr(b, "id", getattr(b, "attr", "")) for b in n.bases]
                members = {m for b in n.body for m in _members(b)}
                old_bases, old_members = self.info.get(n.name, ([], set()))
                # Two classes of one name: merged - a stricter check, never a looser one.
                self.info[n.name] = (old_bases + bases, old_members | members)

    def is_controller(self, name: str, seen: tuple[str, ...] = ()) -> bool:
        if name == "Document":
            return True
        if name in seen or name not in self.info:
            return False
        return any(self.is_controller(b, (*seen, name)) for b in self.info[name][0])

    def members(self, name: str, seen: tuple[str, ...] = ()) -> set[str]:
        if name in seen or name not in self.info:
            return set()
        bases, own = self.info[name]
        return own.union(*(self.members(b, (*seen, name)) for b in bases))


def _members(stmt: ast.stmt) -> Iterator[str]:
    """Attributes a class body statement defines - not field annotations."""
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        yield stmt.name
    elif isinstance(stmt, ast.Assign):
        yield from (t.id for t in stmt.targets if isinstance(t, ast.Name))
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        value = stmt.value
        is_field_default = value is None or (
            (isinstance(value, ast.Constant) and value.value is None)
            or (isinstance(value, ast.List) and not value.elts)
        )
        if "ClassVar" in ast.unparse(stmt.annotation) or not is_field_default:
            yield stmt.target.id


def _document_attrs() -> frozenset[str]:
    from grunt.document.base import _RESERVED, SYS_FIELDS, Document

    public = {a for a in dir(Document) if not a.startswith("_")}
    return frozenset(public | set(_RESERVED) | set(SYS_FIELDS))


def accepts(c: Candidate, receiver: str, classes: _Classes, doc_attrs: frozenset[str]) -> bool:
    """Whether the site is safe to rewrite, the receiver's type being *receiver*."""
    receiver = receiver.removeprefix("Self@")
    if receiver == "AttrDict":
        return c.kind in ("sub", "get") and c.key not in _DICT_ATTRS
    if classes.is_controller(receiver) and c.kind in ("get", "datasub", "dataget"):
        if c.key in doc_attrs | classes.members(receiver):
            return not c.store and c.key in _READABLE_SYS
        return True
    return False


# Running


def python_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if _SKIP_DIRS.intersection(rel.parts) or str(rel).startswith(_SKIP_FILES):
            continue
        yield p


def _reveal_types(pyright_stdout: str) -> dict[str, str]:
    types = {}
    for d in json.loads(pyright_stdout).get("generalDiagnostics", []):
        m = _MISMATCH.search(d.get("message", ""))
        if m:
            types[m[1]] = m[2]
    return types


def run(app_root: Path, class_roots: list[Path], pyright: list[str]) -> Result:
    """Probe *app_root* with pyright and work out the rewrites (nothing written).

    *class_roots* - the trees whose controller classes the app uses (itself, grunt).
    The probed files are restored before this returns, whatever happens.
    """
    result = Result()
    sources: dict[Path, str] = {}
    found: dict[Path, list[Candidate]] = {}
    for p in python_files(app_root):
        text = p.read_text()
        try:
            cands = find_candidates(text, start=result.candidates)
        except SyntaxError:
            continue
        if cands:
            sources[p], found[p] = text, cands
            result.candidates += len(cands)

    try:
        for p, cands in found.items():
            p.write_text(probe_source(sources[p], cands))
        proc = subprocess.run(
            [*pyright, "--outputjson"], cwd=app_root, capture_output=True, text=True, check=False
        )
    finally:
        for p, text in sources.items():
            p.write_text(text)
    types = _reveal_types(proc.stdout)
    result.probed = len(types)

    classes = _Classes()
    for root in class_roots:
        for p in python_files(root):
            try:
                classes.add(p.read_text())
            except SyntaxError:
                continue
    doc_attrs = _document_attrs()

    for p, cands in found.items():
        ok = []
        for c in cands:
            receiver = types.get(c.id)
            if receiver is None:
                continue
            if accepts(c, receiver, classes, doc_attrs):
                ok.append(c)
            else:
                result.kept[receiver] += 1
        if ok:
            result.files[p] = rewrite_source(sources[p], ok)
            result.rewrites += len(ok)
    return result
