"""Security PoC: the Server Script sandbox must not expose a path from the
builtins it provides to arbitrary already-imported modules.

``build_safe_globals`` injects live stdlib module objects (``re``, ``json``,
``math``) into the restricted builtins. RestrictedPython's ``safer_getattr``
only blocks underscore-prefixed names, so a chain of *public* attributes on
a real module object reaches other modules (and from there, process/filesystem
access) without ever touching an underscore name or the ``import`` statement.

This test asserts the sandbox denies reaching ``sys.modules`` through an
exposed module. It FAILS against the current implementation (the escape is
live); it must pass once the modules are no longer exposed as raw objects.
"""

from __future__ import annotations

import pytest


class SandboxEscapedError(Exception):
    """Raised when restricted code reached something it must not."""


def _run(source: str):
    from grunt.scripting.safe_globals import build_safe_globals, compile_script

    result = compile_script(source)
    if result.errors:
        pytest.skip("blocked at compile (also acceptable): " + "; ".join(result.errors))
    assert result.code is not None
    g = build_safe_globals()
    exec(result.code, g)  # noqa: S102 - exercising the sandbox boundary on purpose
    return g


def test_exposed_module_cannot_reach_sys_modules():
    # Walk public attributes off an exposed module to the module registry and
    # read a harmless attribute of a module that was never granted (os.name).
    # Reaching it at all proves the boundary is open; no side-effecting call.
    source = "leaked = re.enum.sys.modules['os'].name\n"
    try:
        g = _run(source)
    except Exception:
        # Any runtime block (AttributeError from a guard, etc.) is the
        # secure outcome - the traversal did not complete.
        return
    # Reached here => traversal completed => sandbox is open. This FAILS today.
    raise SandboxEscapedError(f"reached os.name = {g.get('leaked')!r} from inside the sandbox")
