"""Formula field evaluation.

Fields with a non-empty ``formula`` attribute are *computed fields*: their
value is calculated from a Python expression every time the document is saved.

Expression context
------------------
All field values of the current document are available as plain variables:

    # DocType: OrderLine
    # fields: qty (Float), unit_price (Float), total (Float, formula)
    formula = "qty * unit_price"

    # Conditional
    formula = "price * qty * (1 - discount / 100) if discount else price * qty"

Available built-ins (sandboxed — no imports, no file I/O):

    abs, round, min, max, sum, len, str, int, float, bool,
    all, any, sorted, reversed, enumerate, zip, map, filter,
    divmod, pow, True, False, None

If evaluation raises an exception the field is left unchanged and a warning
is logged.  This ensures a bad formula never blocks a save.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from grunt.core.metadata.doctype import DocType

logger = structlog.get_logger()

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


async def compute_formulas(dt: DocType, row: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all formula fields in *row* and return the updated dict."""
    return await _evaluate_formulas(dt, row, "formula")


async def evaluate_read_formulas(dt: DocType, row: dict[str, Any]) -> dict[str, Any]:
    """Evaluate virtual fields with read_formula in *row*."""
    return await _evaluate_formulas(dt, row, "read_formula")


async def _evaluate_formulas(dt: DocType, row: dict[str, Any], attr: str) -> dict[str, Any]:
    """Generic formula evaluator for a specific attribute (formula or read_formula)."""
    formula_fields = [f for f in dt.fields if getattr(f, attr, None)]
    if not formula_fields:
        return row

    # Build evaluation namespace
    from grunt.app import grunt  # noqa: PLC0415

    async def _count(doctype: str, filters: dict[str, Any] | None = None) -> int:
        return await grunt.count(doctype, filters=filters)

    async def _sum(doctype: str, fieldname: str, filters: dict[str, Any] | None = None) -> float:
        # Use grunt.get_list and sum manually or implement grunt.sum
        rows = await grunt.get_list(doctype, filters=filters, fields=[fieldname])
        return sum(float(r.get(fieldname) or 0) for r in rows)

    ns: dict[str, Any] = {
        **_SAFE_BUILTINS,
        "count": _count,
        "sum_docs": _sum,  # renamed to avoid conflict with built-in sum
        "grunt": grunt,
    }
    for k, v in row.items():
        ns[k] = _to_number_if_possible(v)

    for field in formula_fields:
        formula = getattr(field, attr)
        if not formula or not formula.strip():
            continue
        try:
            # Wrap formula in an async function to allow await of helpers
            code = compile(f"async def __f__(): return {formula}", "<string>", "exec")
            exec(code, ns)  # noqa: S102
            result = await ns["__f__"]()
            
            # Auto-await if the formula returned a coroutine (e.g. from an async helper)
            if hasattr(result, "__await__"):
                result = await result
            
            # Coerce result to the field's target type
            coerced = _coerce_result(result, field.fieldtype)
            row[field.fieldname] = coerced
            ns[field.fieldname] = _to_number_if_possible(coerced)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
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
            logger.debug("suppressed_expected_error", exc_info=True)
        try:
            return float(value)
        except ValueError:
            logger.debug("suppressed_expected_error", exc_info=True)
    return value


def _coerce_result(value: Any, fieldtype: str) -> Any:
    """Coerce the formula result to match the field type."""
    if value is None:
        return None
    if fieldtype in ("Int",):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return value
    if fieldtype in ("Float", "Currency", "Percent"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if fieldtype == "Check":
        return bool(value)
    # Data, Text, etc. — convert to string
    if fieldtype in ("Data", "Text", "LongText", "SmallText"):
        return str(value)
    return value
