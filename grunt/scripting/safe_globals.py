"""Sandboxed execution environment for Server Scripts / Script Reports.

SECURITY HISTORY (2026-08-13): the previous implementation ran plain
``exec()`` with a restricted ``__builtins__`` dict, "validated" only by a
text-substring blocklist (rejecting source that literally contained strings
like ``"os."``, ``"import "``, ``"getattr"``, ...). That is not a real
sandbox: attribute traversal from any allowed object reaches arbitrary
already-loaded classes without ever containing a blocked substring, and
trivially so once the target name is built at runtime instead of typed
literally::

    target = chr(80) + chr(111) + chr(112) + chr(101) + chr(110)  # "Popen"
    for c in str.__mro__[-1].__subclasses__():
        if c.__name__ == target:
            c(['id'], stdout=-1).stdout.read()  # arbitrary shell command

This was verified as a working exploit (real shell command execution)
against the old implementation — see
``tests/unit/test_scripting_sandbox.py``, which must never pass again.

RestrictedPython (used by Zope/Plone, and by Frappe for this exact feature)
fixes this at two levels:

- Compile-time: the AST transformer rejects any identifier or attribute
  name starting with ``"_"`` and disallows dangerous syntax outright — so
  ``str.__mro__`` is a *compile* error, not something a runtime blocklist
  has to notice.
- Run-time: every attribute access is routed through a guard function
  (``safer_getattr``), which independently blocks the same class of names
  even when constructed dynamically (as in the payload above) — the two
  layers don't rely on each other, so a single missed pattern can't reopen
  the hole the way the old text blocklist did.

``import``/``eval``/``exec``/``open`` etc. are blocked simply by never being
present in the builtins dict handed to the compiled code (same mechanism
the old sandbox used for *those* names — the difference here is attribute
traversal, not name lookup, was always the real gap).
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from RestrictedPython import CompileResult, compile_restricted_exec, safe_builtins
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
from RestrictedPython.Guards import (
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)
from RestrictedPython.PrintCollector import PrintCollector

# Builtins RestrictedPython's own `safe_builtins` doesn't already provide,
# but that carry no filesystem/network/process access on their own.
_EXTRA_SAFE_BUILTINS: dict[str, Any] = {
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "bytearray": bytearray,
    "enumerate": enumerate,
    "filter": filter,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "reversed": reversed,
    "sum": sum,
    "type": type,
    "all": all,
    "any": any,
    "iter": iter,
    "print": print,
    "Decimal": Decimal,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "StopIteration": StopIteration,
    # Datetime
    "datetime": datetime,
    "date": date,
    "time": time,
    "timedelta": timedelta,
    "timezone": timezone,
    # Math / json / re — safe: no I/O, no process/network access.
    "math": math,
    "json": json,
    "re": re,
}


def compile_script(source: str) -> CompileResult:
    """Compile *source* under RestrictedPython's restrictions.

    ``.errors`` is non-empty when the script isn't safe to run (syntax
    errors and AST-level violations alike); ``.code`` is the exec()-able
    code object otherwise. This is the actual security boundary — the code
    object it returns is the *only* thing that should ever be exec()'d for
    a script that isn't fully trusted host code.
    """
    return compile_restricted_exec(source, filename="<server_script>")


def validate_script(source: str) -> list[str]:
    """Return the list of safety errors for *source* (empty = OK to run).

    Recompiles under the exact same restrictions :func:`compile_script`
    (and therefore ``ServerScriptRunner.execute``) uses, so this can't
    silently diverge from what actually gets executed the way the old
    text-based pre-check did.
    """
    return list(compile_script(source).errors)


def build_safe_globals(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the globals dict RestrictedPython-compiled code executes under.

    Includes the guard hooks (``_getattr_``, ``_getitem_``, ``_getiter_``,
    ``_write_``, ``_print_``, ...) that RestrictedPython-compiled bytecode
    routes attribute/item access, iteration, assignment, and ``print``
    through — required for restricted code to run at all, and where the
    real access control lives (see module docstring).
    """
    builtins = dict(safe_builtins)
    builtins.update(_EXTRA_SAFE_BUILTINS)
    g: dict[str, Any] = {
        "__builtins__": builtins,
        # Required by RestrictedPython's `class` statement codegen.
        "__metaclass__": type,
        "__name__": "server_script",
        "_getattr_": safer_getattr,
        "_getitem_": default_guarded_getitem,
        "_getiter_": default_guarded_getiter,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_write_": full_write_guard,
        "_print_": PrintCollector,
    }
    if extra:
        g.update(extra)
    return g
