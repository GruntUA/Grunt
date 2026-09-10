"""Source-string extractor.

Walks the bench for translatable strings and returns them as a flat list of
``{source, context, kind, origin, plural_source, occurrences}`` dicts:

* Python  — ``_("...")``, ``pgettext("ctx", "...")``, ``ngettext("s", "p", n)``
* Vue/TS  — ``t('...')`` / ``$t("...")`` / ``tn('s', 'p', n)``
  (``"ctx|msg"`` splits into context)
* DocType JSON — ``label`` / ``description`` / ``placeholder`` / Select ``options``
  / status indicators, keyed by the ``meta:`` / ``help:`` / ``hint:`` / ``select:``
  / ``status:`` msgctxt convention

Consumed by ``grunt i18n extract`` (regenerates PO/POT) and by the Translate
app's registry view. Results are cached in-process (see :func:`get_sources`).
"""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

_PY_FUNCS = {"_", "gettext", "pgettext", "ngettext"}
_TS_CALL = re.compile(r"(?<![\w$])\$?t\(\s*(['\"])(.+?)\1")
# tn('1 apple', '{n} apples', n) — the frontend plural helper.
_TS_PLURAL = re.compile(r"(?<![\w$])tn\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3")
# "10", "1.5", "30d", "365d", "50%" — codes / magnitudes, nothing to translate.
_NUMERIC_TOKEN = re.compile(r"^\d+(?:[.,]\d+)?[a-z%]{0,3}$")
_SKIP_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", "tests", "test",
}

# ── in-process cache ────────────────────────────────────────────────────────
_cache: list[dict[str, Any]] | None = None
_cache_at: float = 0.0
_CACHE_TTL = 120.0


def get_sources(*, force: bool = False) -> list[dict[str, Any]]:
    """Cached :func:`extract_all` (TTL 120s)."""
    global _cache, _cache_at
    if not force and _cache is not None and (time.monotonic() - _cache_at) < _CACHE_TTL:
        return _cache
    _cache = extract_all()
    _cache_at = time.monotonic()
    return _cache


def invalidate() -> None:
    global _cache
    _cache = None


def set_cache(rows: list[dict[str, Any]]) -> None:
    """Prime the cache with an already-computed result (used by the scan task)."""
    global _cache, _cache_at
    _cache = rows
    _cache_at = time.monotonic()


# ── walker ─────────────────────────────────────────────────────────────────
def extract_all(
    bench_dir: Path | None = None, origins: set[str] | None = None
) -> list[dict[str, Any]]:
    """Scan every app under ``<bench>/apps`` (or just those in *origins*)."""
    if bench_dir is None:
        from grunt.site.manager import site_manager

        bench_dir = site_manager.bench_dir
    apps_dir = Path(bench_dir) / "apps"

    found: dict[tuple[str, str], dict[str, Any]] = {}

    def add(
        source: str,
        context: str,
        kind: str,
        origin: str,
        where: str,
        plural_source: str = "",
    ) -> None:
        source = (source or "").strip()
        if not source or not _worth_translating(source):
            return
        key = (source, context)
        row = found.get(key)
        if row is None:
            found[key] = {
                "source": source,
                "context": context,
                "kind": kind,
                "origin": origin,
                "plural_source": plural_source,
                "occurrences": [where],
            }
        else:
            if plural_source and not row.get("plural_source"):
                row["plural_source"] = plural_source
            if where not in row["occurrences"]:
                row["occurrences"].append(where)

    for app_dir in sorted(p for p in apps_dir.iterdir() if p.is_dir()):
        origin = "grunt" if app_dir.name == "grunt" else app_dir.name
        if origins is not None and origin not in origins:
            continue
        for path in _iter_files(app_dir):
            rel = str(path.relative_to(apps_dir))
            suffix = path.suffix.lower()
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if suffix == ".py":
                _scan_python(text, rel, origin, add)
            elif suffix in (".vue", ".ts", ".js", ".tsx"):
                _scan_ts(text, rel, origin, add)
            elif suffix == ".json" and f"{path.parent.name}.json" == path.name:
                _scan_doctype_json(text, rel, origin, add)

    return [
        {**row, "occurrences": ", ".join(row["occurrences"][:20])}
        for row in found.values()
    ]


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


def _worth_translating(s: str) -> bool:
    """Filter out numbers / codes: ``10``, ``1.5``, ``30d``, ``50%``, ``—``.

    A string with no letter at all, or a bare magnitude with a tiny unit
    suffix, is never a UI label.
    """
    if not any(ch.isalpha() for ch in s):
        return False
    return not _NUMERIC_TOKEN.match(s)


def _split_ctx(raw: str) -> tuple[str, str]:
    return tuple(raw.split("|", 1)) if "|" in raw else ("", raw)  # type: ignore[return-value]


def _scan_python(text: str, rel: str, origin: str, add) -> None:
    if "gettext" not in text and "pgettext" not in text and "_(" not in text:
        return
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        else:
            name = ""
        if name not in _PY_FUNCS or not node.args:
            continue
        where = f"{rel}:{node.lineno}"
        if name == "pgettext" and len(node.args) >= 2:
            ctx, msg = node.args[0], node.args[1]
            if _is_str(ctx) and _is_str(msg):
                add(msg.value, ctx.value, "code", origin, where)
        elif name == "ngettext" and len(node.args) >= 2:
            sing, plur = node.args[0], node.args[1]
            if _is_str(sing) and _is_str(plur):
                add(sing.value, "", "code", origin, where, plural_source=plur.value)
        elif _is_str(node.args[0]):
            add(node.args[0].value, "", "code", origin, where)


def _is_str(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _scan_ts(text: str, rel: str, origin: str, add) -> None:
    for m in _TS_PLURAL.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        add(m.group(2), "", "code", origin, f"{rel}:{line}", plural_source=m.group(4))
    for m in _TS_CALL.finditer(text):
        context, source = _split_ctx(m.group(2))
        line = text.count("\n", 0, m.start()) + 1
        add(source, context, "code", origin, f"{rel}:{line}")


def _scan_doctype_json(text: str, rel: str, origin: str, add) -> None:
    try:
        dt = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(dt, dict) or "fields" not in dt:
        return
    name = dt.get("name")
    if not name:
        return
    if dt.get("label"):
        add(dt["label"], f"meta:{name}", "meta", origin, rel)
    if dt.get("description"):
        add(dt["description"], f"help:{name}", "meta", origin, rel)
    # label / description / placeholder each get a distinct context so they never
    # collapse into one registry row (mirrors grunt.i18n.meta.translate_doctype_meta).
    _attr_ctx = {"label": "meta", "description": "help", "placeholder": "hint"}
    for field in dt.get("fields") or []:
        fn = field.get("fieldname") or ""
        for attr, prefix in _attr_ctx.items():
            if field.get(attr):
                add(field[attr], f"{prefix}:{name}.{fn}", "meta", origin, rel)
        if field.get("fieldtype") == "Select" and isinstance(field.get("options"), str):
            for opt in field["options"].split("\n"):
                if opt.strip():
                    add(opt, f"select:{name}.{fn}", "meta", origin, rel)
    for ind in dt.get("status_indicators") or []:
        if ind.get("label"):
            add(ind["label"], f"status:{name}", "meta", origin, rel)
