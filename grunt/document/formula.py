"""Formula field evaluation.

Fields with a non-empty ``formula`` attribute are *computed fields*: their
value is calculated from a Python expression every time the document is saved.

Expression context
All field values of the current document are available as plain variables:

    # DocType: OrderLine
    # fields: qty (Float), unit_price (Float), total (Float, formula)
    formula = "qty * unit_price"

    # Conditional
    formula = "price * qty * (1 - discount / 100) if discount else price * qty"

Available built-ins (restricted - no ``__builtins__``, no imports, and
attribute traversal to ``_``-prefixed / ``format`` names is rejected before
evaluation, see ``_formula_is_safe``; a ``formula`` is authored only by a
System Manager, but this keeps it from becoming code execution on every read):

    abs, round, min, max, sum, len, str, int, float, bool,
    all, any, sorted, reversed, enumerate, zip, map, filter,
    divmod, pow, True, False, None

Also in scope: ``now`` (timezone-aware UTC ``datetime``) and ``today`` (its
``date``) - handy for age / expiry / overdue flags.

If evaluation raises an exception the field is left unchanged and a warning
is logged.  This ensures a bad formula never blocks a save.
"""

import ast
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import grunt
from grunt import log
from grunt.document.meta import Meta
from grunt.metadata.field import get_storage_class
lazy from grunt.metadata.doctype import DocType

_SAFE_BUILTINS: dict[str, Any] = {
    "__builtins__": {},
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "all": all,
    "any": any,
    "sorted": sorted,
    "reversed": reversed,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "divmod": divmod,
    "pow": pow,
    "True": True,
    "False": False,
    "None": None,
}


# Attribute names that re-open the "empty builtins" sandbox: every escape from
# an expression sandbox walks object internals (``().__class__.__mro__`` ->
# ``__subclasses__`` -> a class whose module has ``os``) or uses string
# ``.format`` spec traversal (``"{0.__class__}".format(x)``). An empty
# ``__builtins__`` does not stop either - only refusing the attribute access
# does. ``_``-prefixed attrs cover every dunder plus private helpers
# (``grunt.db._session``); the rest are the non-underscore escape vectors:
#  * ``format``/``format_map`` - the format-spec traversal gap;
#  * frame/coroutine/generator/traceback/code attributes - a helper that
#    returns a coroutine (``count(...)``) exposes ``cr_frame`` -> ``f_builtins``
#    -> the real builtins, all without a single ``_``. Blocked by prefix.
_BLOCKED_ATTRS = frozenset({"format", "format_map"})
_BLOCKED_ATTR_PREFIXES = ("cr_", "gi_", "ag_", "f_", "tb_", "co_")


def _attr_is_blocked(name: str) -> bool:
    return name.startswith("_") or name in _BLOCKED_ATTRS or name.startswith(_BLOCKED_ATTR_PREFIXES)


@lru_cache(maxsize=512)
def _formula_is_safe(formula: str) -> bool:
    """Reject a formula expression that could escape the restricted namespace.

    The namespace already withholds ``__builtins__`` and ``import``; the one
    remaining class of escape is attribute traversal, which this blocks at the
    AST level (so ``formula``/``read_formula``, authored by a System Manager,
    cannot turn a document read into arbitrary code execution). Legitimate
    formulas - arithmetic, ``str``/``int``, ``' '.join(...)``, ``.date()``,
    slicing, f-strings, ``count(...)`` - use none of the blocked attributes.

    Cached on the (static, metadata) formula text so a 500-row list does not
    re-parse the same expressions 500 times.
    """
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if _attr_is_blocked(node.attr):
                return False
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            return False
    return True


async def compute_formulas(dt: DocType, row: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all formula fields in *row* and return the updated dict."""
    return await _evaluate_formulas(dt, row, "formula")


async def evaluate_read_formulas(dt: DocType, row: dict[str, Any]) -> dict[str, Any]:
    """Evaluate virtual fields with read_formula in *row*."""
    return await _evaluate_formulas(dt, row, "read_formula")


async def _evaluate_formulas(dt: DocType, row: dict[str, Any], attr: str) -> dict[str, Any]:
    """Generic formula evaluator for a specific attribute (formula or read_formula)."""
    meta = Meta(dt)
    formula_fields = meta.get_formula_fields(attr)
    if not formula_fields:
        return row

    # Build evaluation namespace

    async def _count(doctype: str, filters: dict[str, Any] | None = None) -> int:
        return await grunt.count(doctype, filters=filters)

    async def _sum(doctype: str, fieldname: str, filters: dict[str, Any] | None = None) -> float:
        # Use grunt.get_list and sum manually or implement grunt.sum
        rows = await grunt.get_list(doctype, filters=filters, fields=[fieldname])
        return sum(float(r.get(fieldname) or 0) for r in rows)

    _now = datetime.now(UTC)
    # NB: ``grunt`` is deliberately NOT exposed here - a formula only needs the
    # sanctioned ``count``/``sum_docs`` helpers, and handing it the whole facade
    # widens the namespace (``grunt.new_doc`` etc. running in the reader's
    # context) for no formula in the codebase that uses it.
    ns: dict[str, Any] = {
        **_SAFE_BUILTINS,
        "count": _count,
        "sum_docs": _sum,  # renamed to avoid conflict with built-in sum
        "now": _now,
        "today": _now.date(),
    }
    numeric_fields = meta.get_numeric_fieldnames()
    for k, v in row.items():
        ns[k] = _to_number_if_possible(v) if k in numeric_fields else v

    for field in formula_fields:
        formula = getattr(field, attr)
        if not formula or not formula.strip():
            continue
        if not _formula_is_safe(formula):
            log.warning("formula.unsafe_blocked", doctype=dt.name, field=field.fieldname)
            continue
        try:
            # Wrap formula in an async function to allow await of helpers
            code = compile(f"async def __f__(): return {formula}", "<string>", "exec")
            exec(code, ns)
            result = await ns["__f__"]()

            # Auto-await if the formula returned a coroutine (e.g. from an async helper)
            if hasattr(result, "__await__"):
                result = await result

            # Coerce result to the field's target type
            coerced = _coerce_result(result, field.fieldtype)
            row[field.fieldname] = coerced
            ns[field.fieldname] = _to_number_if_possible(coerced) if field.is_numeric else coerced
        except Exception as exc:
            log.warning(
                "formula.eval_error",
                doctype=dt.name,
                field=field.fieldname,
                formula=formula,
                error=str(exc),
            )

    return row


def _to_number_if_possible(value: Any) -> Any:
    """Try to convert string numbers to int/float for expression evaluation."""
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
    return value


def _coerce_result(value: Any, fieldtype: str) -> Any:
    """Coerce the formula result to match the field type."""
    if value is None:
        return None
    storage = get_storage_class(fieldtype)
    if storage == "int":
        try:
            return int(round(float(value)))
        except TypeError, ValueError:
            return value
    if storage == "float":
        try:
            return float(value)
        except TypeError, ValueError:
            return value
    if storage == "bool":
        return bool(value)
    # Data, Text, etc. - convert to string
    if fieldtype in ("Data", "LongText"):
        return str(value)
    return value
