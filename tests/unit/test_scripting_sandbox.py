"""Regression test for the Server Script sandbox escape (2026-08-13).

The pre-fix implementation ran plain exec() with a restricted __builtins__
dict, "validated" only by a text-substring blocklist. That blocklist never
saw this payload — it builds the target class name at runtime instead of
typing it literally, and reaches it via attribute traversal, which the old
validator didn't restrict at all:

    target = chr(80)+chr(111)+chr(112)+chr(101)+chr(110)  # "Popen"
    for c in str.__mro__[-1].__subclasses__():
        if c.__name__ == target:
            c(['id'], stdout=-1)  # arbitrary shell command execution

This was verified as a *working* exploit against the old implementation —
`validate_script()` returned zero errors, and exec() ran the payload,
producing real shell command output. This test must always fail loudly
(assert the exploit is rejected) — if it ever starts passing (the exploit
succeeding), the sandbox has regressed.
"""

from __future__ import annotations

import pytest

from grunt.scripting.safe_globals import build_safe_globals, compile_script, validate_script
from grunt.scripting.server_script import ServerScriptRunner

# The exact payload that achieved shell command execution against the old
# text-substring "validator" + plain exec() implementation.
_SUBCLASS_TRAVERSAL_EXPLOIT = """
target_name = chr(80) + chr(111) + chr(112) + chr(101) + chr(110)
found = None
for c in str.__mro__[-1].__subclasses__():
    if c.__name__ == target_name:
        found = c
proc = found(['id'], stdout=-1)
grunt.response = {"escaped": True, "output": proc.stdout.read()}
"""

# Bypasses that avoid dunder syntax entirely by going through the object's
# own regular (non-underscore) attributes rather than __class__ walking.
_OTHER_ESCAPE_ATTEMPTS = [
    # Direct dunder access, no obfuscation.
    "x = str.__mro__[-1].__subclasses__()",
    # Reaching __globals__ off a function object.
    "x = (lambda: None).__globals__",
    # __builtins__ off a module-like object.
    "x = ().__class__.__base__.__subclasses__",
]


class TestSandboxEscapeBlocked:
    def test_subclass_traversal_exploit_rejected_by_validate_script(self):
        errors = validate_script(_SUBCLASS_TRAVERSAL_EXPLOIT)
        assert errors, "the exploit must be rejected at validation time"

    def test_subclass_traversal_exploit_rejected_by_compile(self):
        result = compile_script(_SUBCLASS_TRAVERSAL_EXPLOIT)
        assert result.errors, "the exploit must fail to compile"
        assert result.code is None

    @pytest.mark.parametrize("payload", _OTHER_ESCAPE_ATTEMPTS)
    def test_other_dunder_escapes_rejected(self, payload):
        errors = validate_script(payload)
        assert errors, f"expected rejection for: {payload!r}"

    @pytest.mark.asyncio
    async def test_full_execute_pipeline_blocks_exploit(self):
        """End-to-end: ServerScriptRunner.execute() — the actual code path a
        real Server Script document runs through — must refuse to run this,
        not just the standalone validate_script()/compile_script() helpers.
        """
        runner = ServerScriptRunner()
        result = await runner.execute(_SUBCLASS_TRAVERSAL_EXPLOIT)
        assert result.success is False
        assert result.response == {}

    @pytest.mark.asyncio
    async def test_trusted_scripts_are_also_sandboxed(self):
        """`trusted=True` (file-based app scripts) skips the friendlier
        pre-check, but must still run under the same RestrictedPython
        compile — trusted only means "shipped with the app's own source",
        not "gets full unrestricted Python".
        """
        runner = ServerScriptRunner()
        result = await runner.execute(_SUBCLASS_TRAVERSAL_EXPLOIT, trusted=True)
        assert result.success is False


class TestSafeGlobalsNoDangerousNames:
    def test_no_import_builtin(self):
        g = build_safe_globals()
        assert "__import__" not in g["__builtins__"]

    def test_no_eval_or_exec_builtin(self):
        g = build_safe_globals()
        assert "eval" not in g["__builtins__"]
        assert "exec" not in g["__builtins__"]

    def test_no_open_builtin(self):
        g = build_safe_globals()
        assert "open" not in g["__builtins__"]

    def test_no_raw_getattr_or_hasattr(self):
        """Plain (unguarded) getattr/hasattr would let a script reconstruct
        dunder attribute access dynamically even with safer_getattr wired
        as `_getattr_` — they must not be exposed as callable names at all.
        """
        g = build_safe_globals()
        assert "getattr" not in g["__builtins__"]
        assert "hasattr" not in g["__builtins__"]
