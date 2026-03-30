"""Tests for the scripting module — Server Script sandbox and Client Script loading."""

import pytest

from grunt.core.scripting.safe_globals import build_safe_globals, validate_script
from grunt.core.scripting.server_script import ServerScriptRunner, ScriptResult


# ── Safe globals tests ───────────────────────────────────────────────────


class TestBuildSafeGlobals:
    def test_has_builtins(self):
        g = build_safe_globals()
        builtins = g["__builtins__"]
        assert builtins["len"] is len
        assert builtins["int"] is int
        assert builtins["True"] is True

    def test_no_import(self):
        g = build_safe_globals()
        assert "__import__" not in g["__builtins__"]

    def test_has_datetime(self):
        from datetime import datetime
        g = build_safe_globals()
        assert g["__builtins__"]["datetime"] is datetime

    def test_has_json(self):
        import json
        g = build_safe_globals()
        assert g["__builtins__"]["json"] is json

    def test_extra_injected(self):
        g = build_safe_globals(extra={"doc": {"name": "TEST"}})
        assert g["doc"]["name"] == "TEST"


class TestValidateScript:
    def test_valid_script(self):
        errors = validate_script("x = 1 + 2\nresult = x * 3")
        assert errors == []

    def test_syntax_error(self):
        errors = validate_script("def foo(:\n  pass")
        assert len(errors) == 1
        assert "SyntaxError" in errors[0]

    def test_import_blocked(self):
        errors = validate_script("import os")
        assert any("import" in e for e in errors)

    def test_from_import_blocked(self):
        errors = validate_script("from os import path")
        assert any("import" in e or "from" in e for e in errors)

    def test_subprocess_blocked(self):
        errors = validate_script("subprocess.call(['ls'])")
        assert any("subprocess" in e for e in errors)

    def test_eval_blocked(self):
        errors = validate_script("eval('1+1')")
        assert any("eval" in e for e in errors)

    def test_open_blocked(self):
        errors = validate_script("f = open('/etc/passwd')")
        assert any("open" in e for e in errors)


# ── ServerScriptRunner.execute tests ─────────────────────────────────────


class TestServerScriptExecute:
    def setup_method(self):
        self.runner = ServerScriptRunner()

    def test_simple_script(self):
        result = self.runner.execute("x = 1 + 2")
        assert result.success is True
        assert result.error == ""

    def test_script_with_doc(self):
        result = self.runner.execute(
            "grunt.response = {'total': doc['qty'] * doc['rate']}",
            doc={"qty": 5, "rate": 100},
        )
        assert result.success is True
        assert result.response["total"] == 500

    def test_script_output_capture(self):
        result = self.runner.execute('print("hello world")')
        assert result.success is True
        assert "hello world" in result.output

    def test_script_throw(self):
        result = self.runner.execute('grunt.throw("not allowed")')
        assert result.success is False
        assert "not allowed" in result.error

    def test_script_runtime_error(self):
        result = self.runner.execute("x = 1 / 0")
        assert result.success is False
        assert "ZeroDivisionError" in result.error

    def test_script_name_error(self):
        """Accessing undefined names raises an error (os. is blocked by validator)."""
        result = self.runner.execute("os.system('ls')")
        assert result.success is False
        # Blocked at validation stage — contains "os" error message
        assert "os" in result.error.lower()

    def test_blocked_script_rejected(self):
        result = self.runner.execute("import os\nos.system('ls')")
        assert result.success is False
        assert "import" in result.error.lower() or "заборонено" in result.error.lower()

    def test_script_can_use_datetime(self):
        result = self.runner.execute(
            "grunt.response = {'year': datetime.now().year}"
        )
        assert result.success is True
        from datetime import datetime
        assert result.response["year"] == datetime.now().year

    def test_script_can_use_json(self):
        result = self.runner.execute(
            'grunt.response = json.loads(\'{"a": 1}\')'
        )
        assert result.success is True
        assert result.response == {"a": 1}

    def test_script_can_use_math(self):
        result = self.runner.execute(
            "grunt.response = {'pi': round(math.pi, 2)}"
        )
        assert result.success is True
        assert result.response["pi"] == 3.14

    def test_script_can_use_re(self):
        result = self.runner.execute(
            "grunt.response = {'match': bool(re.match(r'^INV-', 'INV-001'))}"
        )
        assert result.success is True
        assert result.response["match"] is True

    def test_script_extra_context(self):
        result = self.runner.execute(
            "grunt.response = {'sum': params['a'] + params['b']}",
            extra_context={"params": {"a": 3, "b": 7}},
        )
        assert result.success is True
        assert result.response["sum"] == 10

    def test_script_flags(self):
        result = self.runner.execute(
            "grunt.flags['skip_email'] = True\n"
            "grunt.response = {'flags': dict(grunt.flags)}"
        )
        assert result.success is True
        assert result.response["flags"]["skip_email"] is True

    def test_doc_mutation(self):
        """Scripts can modify doc dict."""
        doc = {"status": "Draft", "amount": 100}
        result = self.runner.execute(
            "doc['status'] = 'Validated'\ndoc['tax'] = doc['amount'] * 0.2",
            doc=doc,
        )
        assert result.success is True
        assert doc["status"] == "Validated"
        assert doc["tax"] == 20.0


class TestScriptResult:
    def test_success_result(self):
        r = ScriptResult(success=True, output="ok", response={"x": 1})
        assert r.success is True
        assert r.output == "ok"
        assert r.response == {"x": 1}
        assert r.error == ""

    def test_error_result(self):
        r = ScriptResult(success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"
        assert r.response == {}
