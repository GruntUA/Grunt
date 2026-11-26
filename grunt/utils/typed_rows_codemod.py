"""Codemod: a DocType the code names -> its controller class (TYPED_ROWS_PLAN §10).

Rewrites, where the DocType is a string literal or a module-level string
constant and has a controller - in the app, the apps it ``depends_on`` or the core::

    await grunt.get_doc("Order", n)            -> await Order.get_doc(n)
    await grunt.find_doc("Order", n)           -> await Order.find_doc(n)
    await grunt.get_list("Order", fields=[…])  -> await Order.get_list(fields=[…])
    await grunt.db.get_all("Order", …)         -> await grunt.db.get_all(Order, …)
    await grunt.db.get_doc("Order", n)         -> await grunt.db.get_doc(Order, n)
    await grunt.db.get_value("Order", f, [...], as_dict=True) -> (Order, …)

The receiver is checked with pyright (``reveal_type``, as in :mod:`attr_codemod`):
``Module("grunt")`` / ``DocumentAPI`` for the facade, ``GruntDB`` for ``grunt.db`` -
``ctx.get_doc`` of a server script and the like stay as they are.

A row of the class is no dict: what comes back is followed through the function
and the site is rewritten only where every use reads it as a row - ``x.k``,
``x["k"]`` (rewritten to ``x.k``), ``x.get("k")``, ``for``/comprehensions over a
list, ``len``, truth tests, ``is None``. Passed on to another call, it stays. A
single document (and ``grunt.db`` rows) may be returned from an undecorated
function outside ``api/`` - pyright then checks the callers. ``grunt.get_list``
also shapes rows for the API (``__label`` keys, ISO datetimes, read formulas,
always ``name``/``modified_at``), so it is rewritten only where the rows are used
locally, none of those keys are read, and only with the arguments the class
method takes (``include_total`` dropped); ``name``/``modified_at`` read but not
asked for are added to a literal ``fields``.

The class is imported unless that closes an import cycle (the controller's
module already reaches this one) - those sites are reported, not rewritten.

Then pyright runs over the app: a declared type the new value no longer fits
(``AttrDict``/``dict`` in an annotation, reportAssignmentType/ReturnType) is
retyped to the class - and so is the parameter of a function of the same file
the row is passed to (reportArgumentType: ``Sequence[dict]`` -> ``Sequence[Order]``);
a class the new type names is imported when that closes no cycle. ``x["k"]`` on a
controller becomes ``x.k``. A file with any other new error is put back as it
was - or, with ``keep_errors``, kept and its errors listed to fix by hand (mostly
``str | None`` fields the code took for filled).

Tests are left out: they often test the facade itself.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from grunt.apps.required import dependencies
from grunt.utils import codegen
from grunt.utils.attr_codemod import _DICT_ATTRS, _READABLE_SYS, _Classes, _document_attrs

_SKIP_DIRS = {"node_modules", ".venv", "dist", "uploads", "__pycache__", "migrations", "tests"}
_FACADE = {"get_doc", "find_doc", "get_list"}
_DB = {"get_all", "get_doc", "get_value"}
_FACADE_TYPES = {'Module("grunt")', "DocumentAPI"}
_DB_TYPES = {"GruntDB"}
_LIST_KWARGS = {
    "filters",
    "fields",
    "limit",
    "page",
    "order_by",
    "order",
    "ignore_permissions",
    "include_total",
}
_DATE_TYPES = {"Date", "Datetime", "Time"}
_DATETIME_SYS = {"created_at", "modified_at"}
_MISMATCH = re.compile(r'expected "(__T\d+__)" but received "(.*)"')
_MAX_ROUNDS = 4


# Edits on byte offsets of the whole source


class _Text:
    """A source with byte offsets for ``(line, col)`` of :mod:`ast`."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.raw = source.encode()
        self.starts = [0]
        for line in self.raw.splitlines(keepends=True):
            self.starts.append(self.starts[-1] + len(line))

    def off(self, line: int, col: int) -> int:
        return self.starts[line - 1] + col

    def start(self, node: ast.AST) -> int:
        return self.off(node.lineno, node.col_offset)  # type: ignore[attr-defined]

    def end(self, node: ast.AST) -> int:
        return self.off(node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]

    def seg(self, a: int, b: int) -> str:
        return self.raw[a:b].decode()


def _apply(raw: bytes, edits: Iterable[tuple[int, int, str]]) -> str:
    """Apply ``(start, end, text)`` byte edits (non-overlapping)."""
    for a, b, text in sorted(set(edits), reverse=True):
        raw = raw[:a] + text.encode() + raw[b:]
    return raw.decode()


# Finding sites


@dataclass
class Site:
    id: str
    path: Path
    kind: str  # facade / db
    method: str
    doctype: str
    call: ast.Call
    recv: ast.expr


@dataclass
class Result:
    files: dict[Path, str] = field(default_factory=dict)  # rewritten sources
    rewrites: int = 0
    candidates: int = 0
    skipped: Counter[str] = field(default_factory=Counter)  # reason -> sites
    left: list[str] = field(default_factory=list)  # "reason file:line" of each site left
    cycles: list[str] = field(default_factory=list)  # "file:line Cls" not imported
    reverted: dict[str, list[str]] = field(default_factory=dict)  # file -> pyright errors
    # keep_errors: rewritten all the same - file -> pyright errors to fix by hand
    to_fix: dict[str, list[str]] = field(default_factory=dict)

    def merge(self, other: Result) -> None:
        self.files.update(other.files)
        self.rewrites += other.rewrites
        self.candidates += other.candidates
        self.skipped.update(other.skipped)
        self.left += other.left
        self.cycles += other.cycles
        self.reverted.update(other.reverted)
        self.to_fix.update(other.to_fix)


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "literal"`` bound once."""
    found: dict[str, str | None] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        for t in targets:
            if isinstance(t, ast.Name):
                ok = isinstance(value, ast.Constant) and isinstance(value.value, str)
                found[t.id] = value.value if ok and t.id not in found else None  # type: ignore[union-attr]
    return {k: v for k, v in found.items() if v is not None}


def _doctype_arg(call: ast.Call, consts: dict[str, str]) -> str | None:
    if not call.args or isinstance(call.args[0], ast.Starred):
        return None
    a = call.args[0]
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        name = a.value
    elif isinstance(a, ast.Name) and a.id in consts:
        name = consts[a.id]
    else:
        return None
    return name if name.isidentifier() and name[:1].isupper() else None


def find_sites(path: Path, tree: ast.Module, start: int) -> list[Site]:
    consts = _module_constants(tree)
    out: list[Site] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        method = node.func.attr
        if method not in _FACADE | _DB:
            continue
        doctype = _doctype_arg(node, consts)
        if doctype is None:
            continue
        out.append(
            Site(
                id=f"__T{start + len(out)}__",
                path=path,
                kind="",
                method=method,
                doctype=doctype,
                call=node,
                recv=node.func.value,
            )
        )
    return out


# Following the value


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module, ast.Lambda)


def _scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    while not isinstance(node, _SCOPES):
        node = parents[node]
    return node


def _names(scope: ast.AST, name: str) -> list[ast.Name]:
    return [n for n in ast.walk(scope) if isinstance(n, ast.Name) and n.id == name]


@dataclass
class _Use:
    """What following one site found."""

    reason: str | None = None  # why it can't be rewritten
    keys: set[str] = field(default_factory=set)  # row keys read
    stores: set[str] = field(default_factory=set)  # row keys written
    subs: list[ast.Subscript] = field(default_factory=list)  # x["k"] -> x.k

    def bad(self, reason: str) -> bool:
        self.reason = self.reason or reason
        return False


def _key(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_test(node: ast.AST, parent: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """*node* is only tested for truth / None-ness - its value goes nowhere."""
    if isinstance(parent, ast.If | ast.While | ast.IfExp | ast.Assert) and parent.test is node:
        return True
    if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.Not):
        return True
    if isinstance(parent, ast.Compare) and all(
        isinstance(o, ast.Is | ast.IsNot) for o in parent.ops
    ):
        return True
    if isinstance(parent, ast.comprehension) and node in parent.ifs:
        return True
    # `a or b`: the value of the whole goes on - a test only where the whole is one.
    return isinstance(parent, ast.BoolOp) and _is_test(parent, parents[parent], parents)


def _decorated_or_api(scope: ast.AST, path: Path) -> bool:
    if "api" in path.parts:
        return True
    return isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef) and bool(scope.decorator_list)


class _Follow:
    def __init__(self, path: Path, parents: dict[ast.AST, ast.AST], may_return: bool) -> None:
        self.path = path
        self.parents = parents
        self.may_return = may_return
        self.use = _Use()

    def _once(self, scope: ast.AST, name: str) -> bool:
        stores = [n for n in _names(scope, name) if not isinstance(n.ctx, ast.Load)]
        return len(stores) == 1

    def row(self, expr: ast.expr) -> bool:
        """*expr* is a row (a document): is it only read as one?"""
        p = self.parents[expr]
        if isinstance(p, ast.Attribute) and p.value is expr:
            k = p.attr
            gp = self.parents[p]
            if k == "get" and isinstance(gp, ast.Call) and gp.func is p:
                key = _key(gp.args[0]) if gp.args and not gp.keywords else None
                if key is None or len(gp.args) > 2:
                    return self.use.bad("dict method")
                self.use.keys.add(key)
                return True
            if k in _DICT_ATTRS:
                return self.use.bad("dict method")
            (self.use.stores if isinstance(p.ctx, ast.Store) else self.use.keys).add(k)
            return True
        if isinstance(p, ast.Subscript) and p.value is expr:
            key = _key(p.slice)
            if key is None or not key.isidentifier() or isinstance(p.ctx, ast.Del):
                return self.use.bad("non-literal key")
            (self.use.stores if isinstance(p.ctx, ast.Store) else self.use.keys).add(key)
            self.use.subs.append(p)
            return True
        if _is_test(expr, p, self.parents):
            return True
        if isinstance(p, ast.Return) and self.may_return:
            return True
        return self.use.bad(
            "returned" if isinstance(p, ast.Return) else f"passed on: {type(p).__name__}"
        )

    def row_var(self, scope: ast.AST, name: str) -> bool:
        if not self._once(scope, name):
            return self.use.bad("rebound")
        return all(self.row(n) for n in _names(scope, name) if isinstance(n.ctx, ast.Load))

    def rows(self, expr: ast.expr) -> bool:
        """*expr* is a list of rows."""
        p = self.parents[expr]
        if isinstance(p, ast.For | ast.AsyncFor | ast.comprehension) and p.iter is expr:
            if not isinstance(p.target, ast.Name):
                return self.use.bad("unpacked")
            scope = self.parents[p] if isinstance(p, ast.comprehension) else _scope(p, self.parents)
            return self.row_var(scope, p.target.id)
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "len":
            return True
        if (
            isinstance(p, ast.Subscript)
            and p.value is expr
            and isinstance(p.ctx, ast.Load)
            and isinstance(p.slice, ast.Constant | ast.UnaryOp)
        ):
            return self.row(p)
        if _is_test(expr, p, self.parents):
            return True
        if isinstance(p, ast.Return) and self.may_return:
            return True
        return self.use.bad(
            "returned" if isinstance(p, ast.Return) else f"passed on: {type(p).__name__}"
        )

    def site(self, value: ast.expr, many: bool) -> bool:
        """*value* - the awaited call."""
        p = self.parents[value]
        if isinstance(p, ast.Assign | ast.AnnAssign) and p.value is value:
            targets = p.targets if isinstance(p, ast.Assign) else [p.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                return self.use.bad("assigned to non-name")
            scope = _scope(p, self.parents)
            name = targets[0].id
            if not self._once(scope, name):
                return self.use.bad("rebound")
            loads = [n for n in _names(scope, name) if isinstance(n.ctx, ast.Load)]
            check = self.rows if many else self.row
            return all(check(n) for n in loads)
        return self.rows(value) if many else self.row(value)


# Deciding


@dataclass
class _Controller:
    name: str
    module: str
    path: Path
    top: Path
    fields: dict[str, dict]


class _Controllers:
    def __init__(self, tops: list[Path]) -> None:
        self.tops = tops
        self.cache: dict[str, _Controller | None] = {}

    def get(self, doctype: str) -> _Controller | None:
        if doctype not in self.cache:
            self.cache[doctype] = self._find(doctype)
        return self.cache[doctype]

    def _find(self, doctype: str) -> _Controller | None:
        py = codegen._find_controller(doctype, self.tops)
        if py is None:
            return None
        top = codegen._package_top(py)
        if top is None:
            return None
        fields: dict[str, dict] = {}
        for js in py.parent.glob("*.json"):
            try:
                data = json.loads(js.read_text(encoding="utf-8"))
            except OSError, ValueError:
                continue
            if isinstance(data, dict) and data.get("name") == doctype:
                fields = {f["fieldname"]: f for f in data.get("fields", []) if "fieldname" in f}
        return _Controller(doctype, codegen._module_name(py, top), py, top, fields)


def _bound_names(tree: ast.Module) -> dict[str, str | None]:
    """Module-level name -> the module it is imported from (``None``: defined here)."""
    out: dict[str, str | None] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and not node.level:
            for a in node.names:
                out[a.asname or a.name] = (
                    f"{node.module}.{a.name}" if (a.asname in (None, a.name)) else "?"
                )
        elif isinstance(node, ast.Import):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0]] = "?"
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out[node.name] = None
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = "?"
    return out


@dataclass
class _Plan:
    site: Site
    ctrl: _Controller
    use: _Use
    fields_add: list[str]


class Rewriter:
    def __init__(self, classes: _Classes, controllers: _Controllers) -> None:
        self.classes = classes
        self.controllers = controllers
        self.doc_attrs = _document_attrs()

    def plan(self, site: Site, tree: ast.Module, parents: dict, result: Result) -> _Plan | None:
        def skip(reason: str) -> None:
            result.skipped[reason] += 1
            result.left.append(f"{reason} {site.path}:{call.lineno}")

        call = site.call
        ctrl = self.controllers.get(site.doctype)
        if ctrl is None:
            skip("no controller")
            return None
        if site.kind == "db":
            if site.method == "get_all" and any(k.arg == "pluck" for k in call.keywords):
                skip("pluck")
                return None
            if site.method == "get_value" and not any(
                k.arg == "as_dict" and isinstance(k.value, ast.Constant) and k.value.value is True
                for k in call.keywords
            ):
                skip("get_value without as_dict")
                return None
        if site.method == "get_list" and site.kind == "facade":
            extra = {k.arg for k in call.keywords} - _LIST_KWARGS
            if extra or len(call.args) > 1:
                skip("get_list arguments")
                return None
        if any(k.arg is None for k in call.keywords):
            skip("**kwargs")
            return None

        value = parents[call]
        if not isinstance(value, ast.Await):
            skip("not awaited")
            return None
        scope = _scope(call, parents)
        if isinstance(scope, ast.Module):
            skip("module level")
            return None
        many = site.method in ("get_list", "get_all")
        facade_list = site.kind == "facade" and site.method == "get_list"
        follow = _Follow(
            site.path, parents, not facade_list and not _decorated_or_api(scope, site.path)
        )
        if not follow.site(value, many):
            skip(follow.use.reason or "?")
            return None
        use = follow.use

        members = self.classes.members(ctrl.name) | self.doc_attrs
        for k in use.keys | use.stores:
            if k.startswith("_") or "__" in k:
                skip("private key")
                return None
            if k in members and (k not in _READABLE_SYS or k in use.stores):
                skip("key taken by the controller")
                return None
        fields_add: list[str] = []
        if facade_list:
            for k in use.keys | use.stores:
                f = ctrl.fields.get(k, {})
                if k in _DATETIME_SYS or f.get("fieldtype") in _DATE_TYPES:
                    skip("get_list: date read")
                    return None
                if f.get("read_formula"):
                    skip("get_list: read formula")
                    return None
            fields_kw = next((k for k in call.keywords if k.arg == "fields"), None)
            if fields_kw is not None:
                if not isinstance(fields_kw.value, ast.List) or not all(
                    _key(e) for e in fields_kw.value.elts
                ):
                    skip("get_list: fields not a literal")
                    return None
                asked = {_key(e) for e in fields_kw.value.elts}
                fields_add = [k for k in ("name", "modified_at") if k in use.keys - asked]
        return _Plan(site, ctrl, use, fields_add)

    def rewrite_file(
        self,
        path: Path,
        source: str,
        tree: ast.Module,
        found: list[Site],
        types: dict[str, str],
        result: Result,
    ) -> tuple[str | None, int, set[str]]:
        """*source* rewritten (``None``: nothing to), the sites rewritten, the
        classes it now reads by. *types*: site id -> its receiver's type."""
        parents = _parents(tree)
        text = _Text(source)
        module = _module_of(path)
        bound = _bound_names(tree)
        edits: list[tuple[int, int, str]] = []
        imports: dict[str, set[str]] = defaultdict(set)
        used: set[str] = set()
        n = 0
        for s in found:
            recv = types.get(s.id, "")
            if recv in _FACADE_TYPES and s.method in _FACADE:
                s.kind = "facade"
            elif recv in _DB_TYPES and s.method in _DB:
                s.kind = "db"
            else:
                result.skipped[f"receiver {recv or '?'}"] += 1
                continue
            plan = self.plan(s, tree, parents, result)
            if plan is None:
                continue
            ctrl = plan.ctrl
            have = bound.get(ctrl.name, "missing")
            if ctrl.path.resolve() == path.resolve() or have == f"{ctrl.module}.{ctrl.name}":
                pass  # defined or imported here already
            elif have != "missing":
                result.skipped["class name taken"] += 1
                continue
            elif self._cycle(path, module, ctrl):
                result.cycles.append(f"{path}:{s.call.lineno} {ctrl.name}")
                result.skipped["import cycle"] += 1
                continue
            else:
                imports[ctrl.module].add(ctrl.name)
            edits += self.edits(plan, text)
            used.add(ctrl.name)
            n += 1
        if not edits:
            return None, 0, used
        out = _apply(text.raw, edits)
        for mod, names in imports.items():
            out = codegen._ensure_import(out, mod, sorted(names))
        return out, n, used

    @staticmethod
    def _cycle(path: Path, module: str | None, ctrl: _Controller) -> bool:
        """Whether importing *ctrl* into *path* closes an import cycle (or the
        core would import an app)."""
        if module is None:
            return True
        package = module.split(".")[0]
        if package != ctrl.module.split(".")[0]:
            # Another package: an app may import the core, never the other way;
            # an app it depends on - unless that one imports this package back.
            return package == "grunt" or package in _packages_imported(ctrl.top)
        try:
            return codegen._imports_reach(ctrl.top, ctrl.module, module)
        except SyntaxError:
            return True

    def edits(self, plan: _Plan, text: _Text) -> list[tuple[int, int, str]]:
        site, call = plan.site, plan.site.call
        cls = plan.ctrl.name
        out: list[tuple[int, int, str]] = []
        first = call.args[0]
        if site.kind == "db":
            out.append((text.start(first), text.end(first), cls))
        else:
            out.append((text.start(site.recv), text.end(site.recv), cls))
            nxt = [*call.args[1:], *call.keywords]
            if nxt:
                out.append((text.start(first), text.start(min(nxt, key=text.start)), ""))
            else:
                out.append((text.start(first), text.end(call) - 1, ""))
            for i, kw in enumerate(call.keywords):
                if kw.arg == "include_total":
                    before = [*call.args[1:], *call.keywords[:i]]
                    a = text.end(max(before, key=text.end)) if before else text.start(kw)
                    b = text.end(kw)
                    if not before:
                        after = call.keywords[i + 1 :]
                        b = text.start(after[0]) if after else text.end(call) - 1
                    out.append((a, b, ""))
                if kw.arg == "fields" and plan.fields_add:
                    lst = kw.value
                    assert isinstance(lst, ast.List)
                    added = ", ".join(f'"{k}"' for k in plan.fields_add)
                    if lst.elts:
                        pos = text.end(lst.elts[-1])
                        out.append((pos, pos, f", {added}"))
                    else:
                        pos = text.end(lst) - 1
                        out.append((pos, pos, added))
        for sub in plan.use.subs:
            key = _key(sub.slice)
            out.append((text.end(sub.value), text.end(sub), f".{key}"))
        return out


# Running


def python_files(root: Path, only: Path | None = None) -> Iterator[Path]:
    base = only or root
    files = [base] if base.is_file() else sorted(base.rglob("*.py"))
    for p in files:
        rel = p.relative_to(root)
        if (
            _SKIP_DIRS.intersection(rel.parts)
            or p.name.startswith("test_")
            or p.name == "conftest.py"
        ):
            continue
        if str(rel).startswith(("grunt/document/api.py", "grunt/db/api.py")):
            continue
        yield p


def _pyright(pyright: list[str], root: Path) -> list[dict]:
    proc = subprocess.run(
        [*pyright, "--outputjson"], cwd=root, capture_output=True, text=True, check=False
    )
    try:
        return json.loads(proc.stdout).get("generalDiagnostics", [])
    except ValueError:
        raise RuntimeError(f"pyright failed: {proc.stderr or proc.stdout}") from None


def _errors(diags: list[dict]) -> list[dict]:
    return [d for d in diags if d.get("severity") == "error" and not _MISMATCH.search(d["message"])]


def _new_errors(before: list[dict], after: list[dict]) -> list[dict]:
    """Errors of *after* not in *before* - matched by file, rule and message."""
    seen = Counter((d["file"], d.get("rule"), d["message"]) for d in before)
    out = []
    for d in after:
        key = (d["file"], d.get("rule"), d["message"])
        if seen[key]:
            seen[key] -= 1
        else:
            out.append(d)
    return out


_RECEIVED = re.compile(r'Type "([^"]*)" is not assignable to (?:declared|return) type "([^"]*)"')
_NO_ITEM = re.compile(r'"__(?:get|set)item__" method not defined on type "(\w+)"')
_ARGUMENT = re.compile(
    r'Argument of type "([^"]*)" cannot be assigned to parameter "(\w+)" of type "[^"]*"'
    r' in function "(\w+)"'
)
_ROW_TYPE = re.compile(r"\b(AttrDict|dict|Mapping)\b")


def _row_type_to(annotation: str, cls: str) -> str | None:
    """*annotation* with each row type in it (``AttrDict``, ``dict[…]``,
    ``Mapping[…]``) replaced by *cls* - ``list[dict[str, Any]] | None`` ->
    ``list[Order] | None``; ``None`` when it has none."""
    out, pos, found = [], 0, False
    for m in _ROW_TYPE.finditer(annotation):
        if m.start() < pos:
            continue  # inside the brackets of one already replaced
        end = m.end()
        if annotation[end : end + 1] == "[":
            depth = 0
            for i in range(end, len(annotation)):
                depth += {"[": 1, "]": -1}.get(annotation[i], 0)
                if depth == 0:
                    end = i + 1
                    break
            else:
                return None
        out += [annotation[pos : m.start()], cls]
        pos, found = end, True
    return "".join([*out, annotation[pos:]]) if found else None


_BUILTIN_TYPES = {"list", "dict", "tuple", "set", "str", "int", "float", "bool", "None"}


class _Fixer:
    """One round of pyright fixes for one file."""

    def __init__(
        self,
        source: str,
        bound: set[str],
        classes: _Classes,
        doc_attrs: frozenset[str],
        importer: Callable[[str], str | None] | None = None,
    ):
        """*importer*: a controller class -> the module to import it from here
        (``None``: it can't be, e.g. an import cycle)."""
        self.source = source
        self.text = _Text(source)
        self.tree = ast.parse(source)
        self.parents = _parents(self.tree)
        self.bound = bound
        self.classes = classes
        self.doc_attrs = doc_attrs
        self.edits: list[tuple[int, int, str]] = []
        self.importer = importer
        self.imports: dict[str, set[str]] = defaultdict(set)

    def _bind(self, names: set[str]) -> bool:
        """Whether each of *names* is bound here - importing the controller
        classes that are not yet, when they can be."""
        todo: dict[str, str] = {}
        for n in names - self.bound - _BUILTIN_TYPES:
            module = self.importer(n) if self.importer and self.classes.is_controller(n) else None
            if module is None:
                return False
            todo[n] = module
        for n, module in todo.items():
            self.imports[module].add(n)
            self.bound.add(n)
        return True

    def _offset(self, pos: dict) -> int:
        line = pos["line"] + 1
        chars = self.source.splitlines(keepends=True)[pos["line"]][: pos["character"]]
        return self.text.off(line, len(chars.encode()))

    def _at(self, d: dict, kind: type | tuple[type, ...]) -> list[ast.AST]:
        a = self._offset(d["range"]["start"])
        return [
            n
            for n in ast.walk(self.tree)
            if isinstance(n, kind)
            and hasattr(n, "lineno")
            and self.text.start(n) <= a < self.text.end(n)
        ]

    def fix(self, d: dict) -> bool:
        """Fix the pyright error *d*; ``False`` (nothing recorded): it can't be."""
        edits, bound = len(self.edits), set(self.bound)
        imports = {m: set(n) for m, n in self.imports.items()}
        if self._fix(d) and not self._conflicts(edits):
            return True
        del self.edits[edits:]
        self.bound, self.imports = bound, defaultdict(set, imports)
        return False

    def _conflicts(self, since: int) -> bool:
        """Whether an edit from *since* on overlaps an earlier one that is not the
        same - e.g. one parameter retyped to ``Order`` by one call, ``Invoice`` by
        another."""
        done = self.edits[:since]
        for a, b, t in self.edits[since:]:
            for c, e, u in done:
                if (a, b, t) != (c, e, u) and a < e and c < b or (a == b == c == e and t != u):
                    return True
        return False

    def _fix(self, d: dict) -> bool:
        rule, msg = d.get("rule"), d["message"]
        m = _RECEIVED.search(msg)
        if m and rule in ("reportAssignmentType", "reportReturnType"):
            received = m[1]
            names = set(re.findall(r"[A-Za-z_]\w*", received))
            if (
                not any(self.classes.is_controller(n) for n in names)
                or names & {"dict", "AttrDict", "Any"}
                or not self._bind(names)
            ):
                return False  # not the class alone: a row mixed with a dict
            if rule == "reportReturnType":
                fn = self._innermost(d, (ast.FunctionDef, ast.AsyncFunctionDef))
                ann = fn.returns if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) else None
            else:
                ann = self._declared(d)
            if ann is None:
                return False
            old = self.text.seg(self.text.start(ann), self.text.end(ann))
            if not re.search(r"\b(AttrDict|dict|Mapping)\b", old):
                return False  # not a row type that the class replaced
            new = received
            if re.search(r"\bNone\b", old) and "None" not in names:
                new = f"{new} | None"
            self.edits.append((self.text.start(ann), self.text.end(ann), new))
            return True
        m = _NO_ITEM.search(msg)
        if m and rule == "reportIndexIssue" and self.classes.is_controller(m[1]):
            subs = [
                s
                for s in self._at(d, ast.Subscript)
                if isinstance(s, ast.Subscript)
                and self.text.start(s.value) == self._offset(d["range"]["start"])
            ]
            if not subs:
                return False
            sub = subs[-1]
            key = _key(sub.slice)  # type: ignore[attr-defined]
            if not key or not key.isidentifier() or key.startswith("_"):
                return False
            store = isinstance(sub.ctx, ast.Store)  # type: ignore[attr-defined]
            members = self.classes.members(m[1]) | self.doc_attrs
            if key in members and (store or key not in _READABLE_SYS):
                return False
            self.edits.append((self.text.end(sub.value), self.text.end(sub), f".{key}"))  # type: ignore[attr-defined]
            return True
        m = _ARGUMENT.search(msg)
        if m and rule == "reportArgumentType":
            return self._retype_parameter(d, m[1], m[2], m[3])
        return False

    def _retype_parameter(self, d: dict, received: str, param: str, fn_name: str) -> bool:
        """A row passed to a function of this file whose parameter still says
        ``dict``/``AttrDict``: the parameter takes the class (``Sequence[dict]``
        -> ``Sequence[Order]``). Other callers that pass dicts then fail
        pyright, and the file is put back."""
        names = set(re.findall(r"[A-Za-z_]\w*", received))
        ctrls = {n for n in names if self.classes.is_controller(n)}
        if len(ctrls) != 1 or names & {"dict", "AttrDict", "Any"} or not self._bind(names):
            return False
        cls = ctrls.pop()
        calls = [
            c
            for c in self._at(d, ast.Call)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", getattr(c.func, "attr", None)) == fn_name
        ]
        if not calls:
            return False
        fn = self._callee(min(calls, key=lambda c: self.text.end(c) - self.text.start(c)))
        if fn is None:
            return False
        a = fn.args
        arg = next((x for x in [*a.posonlyargs, *a.args, *a.kwonlyargs] if x.arg == param), None)
        if arg is None or arg.annotation is None:
            return False
        ann = arg.annotation
        new = _row_type_to(self.text.seg(self.text.start(ann), self.text.end(ann)), cls)
        if new is None:
            return False
        self.edits.append((self.text.start(ann), self.text.end(ann), new))
        return True

    def _callee(self, call: ast.Call) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        """The function of this file *call* calls: ``f(…)`` - module level,
        ``self.f(…)`` / ``cls.f(…)`` - a method of the enclosing class."""
        func = call.func
        if isinstance(func, ast.Name):
            body: list[ast.stmt] = self.tree.body
            name = func.id
        elif isinstance(func, ast.Attribute) and getattr(func.value, "id", None) in ("self", "cls"):
            node: ast.AST | None = call
            while node is not None and not isinstance(node, ast.ClassDef):
                node = self.parents.get(node)
            if node is None:
                return None
            body, name = node.body, func.attr
        else:
            return None
        defs = [
            n
            for n in body
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == name
        ]
        return defs[0] if len(defs) == 1 else None

    def _innermost(self, d: dict, kind: type | tuple[type, ...]) -> ast.AST | None:
        found = self._at(d, kind)
        return min(found, key=lambda n: self.text.end(n) - self.text.start(n), default=None)

    def _declared(self, d: dict) -> ast.expr | None:
        stmt = self._innermost(d, (ast.Assign, ast.AnnAssign))
        if stmt is None:
            return None
        if isinstance(stmt, ast.AnnAssign):
            return stmt.annotation
        assert isinstance(stmt, ast.Assign)
        target = stmt.targets[0]
        if not isinstance(target, ast.Name):
            return None
        scope = _scope(stmt, self.parents)
        decl = [
            n
            for n in ast.walk(scope)
            if isinstance(n, ast.AnnAssign)
            and isinstance(n.target, ast.Name)
            and n.target.id == target.id
        ]
        return decl[0].annotation if len(decl) == 1 else None

    def result(self) -> str:
        # One parameter or annotation fixed from several errors: one edit.
        out = _apply(self.text.raw, list(dict.fromkeys(self.edits)))
        for module, names in self.imports.items():
            out = codegen._ensure_import(out, module, sorted(names))
        return _drop_unused(out, "AttrDict")


def _drop_unused(source: str, name: str) -> str:
    """Drop *name* from a one-line ``from … import`` once nothing else uses it."""
    tree = ast.parse(source)
    if any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(tree)) or re.search(
        rf'["\'][^"\']*\b{name}\b', source
    ):
        return source
    lines = source.splitlines(keepends=True)
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.lineno == node.end_lineno
            and any(a.name == name and a.asname is None for a in node.names)
        ):
            rest = [a for a in node.names if a.name != name]
            if rest:
                lines[node.lineno - 1] = (
                    codegen._from_import(
                        node.module or "",
                        [a.name if not a.asname else f"{a.name} as {a.asname}" for a in rest],
                    )
                    + "\n"
                )
            else:
                lines[node.lineno - 1] = ""
            return "".join(lines)
    return source


def _module_of(path: Path) -> str | None:
    top = codegen._package_top(path)
    return codegen._module_name(path, top) if top else None


def _imports(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.add(n.module)
            out.update(f"{n.module}.{a.name}" for a in n.names)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


def run(
    app_root: Path,
    class_roots: list[Path],
    pyright: list[str],
    only: Path | None = None,
    keep_errors: bool = False,
) -> Result:
    """Work out the rewrites of *app_root* (or of the files under *only*), checked
    by pyright over the whole app. Nothing is left written: the files are
    restored before this returns, whatever happens.

    *keep_errors*: a file pyright then fails on is kept rewritten (the errors
    that can be fixed are), the rest go to ``Result.to_fix`` - to finish by hand."""
    result = Result()
    app_root = app_root.resolve()
    sources: dict[Path, str] = {}
    trees: dict[Path, ast.Module] = {}
    sites: dict[Path, list[Site]] = {}
    for p in python_files(app_root, only):
        text = p.read_text()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        found = find_sites(p, tree, result.candidates)
        if found:
            sources[p], trees[p], sites[p] = text, tree, found
            result.candidates += len(found)

    deps = _dependency_roots(app_root)
    tops = list(dict.fromkeys([*_tops(app_root), *(t for d in deps for t in _tops(d))]))
    controllers = _Controllers([*tops, codegen._CORE_PACKAGE])
    classes = _Classes()
    for root in dict.fromkeys([*class_roots, *deps]):
        for p in python_files_all(root):
            try:
                classes.add(p.read_text())
            except SyntaxError:
                continue
    rewriter = Rewriter(classes, controllers)

    written: set[Path] = set()
    all_sources: dict[Path, str] = {}

    def write(p: Path, text: str) -> None:
        all_sources.setdefault(p, p.read_text())
        p.write_text(text)
        written.add(p)

    try:
        # 1. Receiver types
        for p, found in sites.items():
            t = _Text(sources[p])
            edits = []
            for s in found:
                edits.append((t.start(s.recv), t.start(s.recv), "reveal_type("))
                edits.append((t.end(s.recv), t.end(s.recv), f', expected_text="{s.id}")'))
            write(p, _apply(t.raw, edits))
        probe = _pyright(pyright, app_root)
        types = {m[1]: m[2] for d in probe if (m := _MISMATCH.search(d["message"]))}
        before = _errors(probe)
        for p in list(written):
            p.write_text(all_sources[p])

        # 2. Plans
        new: dict[Path, str] = {}
        classes_in: dict[Path, set[str]] = defaultdict(set)
        counts: dict[Path, int] = {}
        for p, found in sites.items():
            out, n, used = rewriter.rewrite_file(p, sources[p], trees[p], found, types, result)
            if out is not None:
                new[p], counts[p], classes_in[p] = out, n, used

        # 3. Pyright: retype annotations, x["k"] -> x.k; put back what still fails
        doc_attrs = rewriter.doc_attrs
        for p, text in new.items():
            write(p, text)
        for _ in range(_MAX_ROUNDS):
            after = _errors(_pyright(pyright, app_root))
            fresh = _new_errors(before, after)
            if not fresh:
                break
            by_file: dict[Path, list[dict]] = defaultdict(list)
            for d in fresh:
                by_file[Path(d["file"])].append(d)
            changed = False
            for f, errs in by_file.items():
                f = f.resolve()
                current = f.read_text()
                fixer = _Fixer(
                    current,
                    set(_bound_names(ast.parse(current))) | classes_in.get(f, set()),
                    classes,
                    doc_attrs,
                    importer=_importer(f, controllers),
                )
                if keep_errors:
                    if [d for d in errs if fixer.fix(d)]:
                        write(f, fixer.result())
                        new[f] = fixer.result()
                        changed = True
                    continue
                if all(fixer.fix(d) for d in errs):
                    write(f, fixer.result())
                    new[f] = fixer.result()
                    changed = True
                    continue
                culprits = [f] if f in new else _culprits(f, new)
                for c in culprits:
                    if c in new:
                        result.reverted[str(c.relative_to(app_root))] = [_describe(d) for d in errs]
                        del new[c]
                        write(c, all_sources[c])
                        changed = True
            if not changed:
                break
        else:
            # Out of rounds: put back what still fails - and what failed only
            # with it - until pyright reports nothing new.
            while not keep_errors and new:
                put_back = False
                for d in _new_errors(before, _errors(_pyright(pyright, app_root))):
                    f = Path(d["file"]).resolve()
                    for c in [f] if f in new else _culprits(f, new):
                        if c in new:
                            result.reverted.setdefault(str(c.relative_to(app_root)), []).append(
                                _describe(d)
                            )
                            del new[c]
                            write(c, all_sources[c])
                            put_back = True
                if not put_back:
                    break
        if keep_errors:
            for d in _new_errors(before, _errors(_pyright(pyright, app_root))):
                f = Path(d["file"]).resolve()
                rel = str(f.relative_to(app_root)) if f.is_relative_to(app_root) else str(f)
                result.to_fix.setdefault(rel, []).append(_describe(d))
        result.files = {p: t for p, t in new.items() if t != all_sources.get(p, sources.get(p))}
        result.rewrites = sum(counts.get(p, 0) for p in result.files)
        result.cycles = [c.removeprefix(f"{app_root}/") for c in result.cycles]
    finally:
        for p in written:
            p.write_text(all_sources[p])
    return result


@cache
def _packages_imported(top: Path) -> frozenset[str]:
    """Top-level packages the modules of *top* import (anywhere in a module)."""
    found: set[str] = set()
    for p in top.rglob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except OSError, SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module and not n.level:
                found.add(n.module.split(".")[0])
            elif isinstance(n, ast.Import):
                found.update(a.name.split(".")[0] for a in n.names)
    return frozenset(found)


def _importer(path: Path, controllers: _Controllers) -> Callable[[str], str | None]:
    """Controller class -> the module *path* may import it from (no cycle)."""
    module = _module_of(path)

    def find(name: str) -> str | None:
        ctrl = controllers.get(name)
        if ctrl is None or ctrl.path.resolve() == path or Rewriter._cycle(path, module, ctrl):
            return None
        return ctrl.module

    return find


def _describe(d: dict) -> str:
    line = d["range"]["start"]["line"] + 1
    return f"{Path(d['file']).name}:{line} {d['message'].splitlines()[0]}"


def _culprits(path: Path, new: dict[Path, str]) -> list[Path]:
    """The rewritten files *path* imports (a retyped return reaches it from there)."""
    try:
        imported = _imports(ast.parse(path.read_text()))
    except OSError, SyntaxError:
        return list(new)
    found = [p for p in new if _module_of(p) in imported]
    return found or list(new)


def _dependency_roots(root: Path) -> list[Path]:
    """The apps *root* ``depends_on``, transitively (sibling folders that exist):
    their DocTypes are read by class too - an app may import the apps it needs."""
    out: list[Path] = []
    queue = [root]
    while queue:
        for dep in dependencies(queue.pop()):
            path = (root.parent / dep.name).resolve()
            if path != root and path not in out and (path / "pyproject.toml").exists():
                out.append(path)
                queue.append(path)
    return out


def _tops(root: Path) -> list[Path]:
    """Top packages of the project at *root* (the folders with ``__init__.py``)."""
    return [
        d
        for d in sorted(root.iterdir())
        if d.is_dir() and d.name != "tests" and (d / "__init__.py").exists()
    ]


def python_files_all(root: Path) -> Iterator[Path]:
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if {"node_modules", ".venv", "__pycache__"}.intersection(rel.parts):
            continue
        yield p
