"""`grunt lint`: linters run in parallel, findings are normalised to one report."""

import importlib
import json
import subprocess
import threading

import pytest
from click.testing import CliRunner

# grunt.cli re-exports the `lint` command under the module's name
lint_cli = importlib.import_module("grunt.cli.lint")
Diagnostic = lint_cli.Diagnostic


@pytest.fixture
def bench(tmp_path, monkeypatch):
    for name in ["alpha", "beta"]:
        app = tmp_path / "apps" / name
        app.mkdir(parents=True)
        (app / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')
    (tmp_path / "apps" / "alpha" / "package.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _diag(path, line, code="E1", tool="ruff", fixable=False):
    return Diagnostic(tool, path, line, 1, "error", code, f"bad {code}", fixable)


@pytest.fixture
def linters(monkeypatch):
    """Fake linters: beta's Python fails; both Python tasks must be running at once."""
    calls: list[tuple[str, str]] = []
    started = threading.Barrier(2, timeout=5)

    def python(root, fix, report):
        calls.append((root.name, "python"))
        started.wait()  # BrokenBarrierError unless the tasks run concurrently
        if root.name == "beta":
            report.ok = False
            report.diagnostics += [
                _diag("apps/beta/b.py", 9, fixable=True),
                _diag("apps/beta/a.py", 3, "reportX", "pyright"),
            ]

    def frontend(root, report):
        calls.append((root.name, "frontend"))

    monkeypatch.setattr(lint_cli, "_python_task", python)
    monkeypatch.setattr(lint_cli, "_run_frontend", frontend)
    return calls


def _summary(output):
    return output.split("Summary")[1]


def test_bench_runs_in_parallel_and_reports_problems_sorted(bench, linters):
    result = CliRunner().invoke(lint_cli.lint, ["--path", str(bench), "-j", "4"])

    assert result.exit_code == 1
    assert sorted(linters) == [("alpha", "frontend"), ("alpha", "python"), ("beta", "python")]
    lines = result.output.splitlines()
    first = lines.index("apps/beta/a.py:3:1: error [pyright reportX] bad reportX")
    assert lines[first + 1] == "apps/beta/b.py:9:1: error [ruff E1, fixable] bad E1"
    summary = _summary(result.output)
    assert "✗ beta  2 errors (pyright 1, ruff 1)" in summary
    assert "1 of 2 OK" in summary
    assert "1 fixable with `grunt lint --fix`" in summary


def test_frontend_task_only_for_apps_with_package_json(bench, linters):
    CliRunner().invoke(lint_cli.lint, ["--path", str(bench), "-j", "2"])

    assert ("beta", "frontend") not in linters


def test_json_format_is_a_single_document(bench, linters):
    result = CliRunner().invoke(lint_cli.lint, ["--path", str(bench), "--format", "json"])

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["ok"] is False
    assert [(a["name"], a["ok"]) for a in report["apps"]] == [("alpha", True), ("beta", False)]
    assert [(d["app"], d["path"], d["line"]) for d in report["diagnostics"]] == [
        ("beta", "apps/beta/a.py", 3),
        ("beta", "apps/beta/b.py", 9),
    ]


def test_crashing_linter_fails_only_its_app(bench, linters, monkeypatch):
    def boom(root, report):
        raise RuntimeError("npm exploded")

    monkeypatch.setattr(lint_cli, "_python_task", lambda root, fix, report: None)
    monkeypatch.setattr(lint_cli, "_run_frontend", boom)

    result = CliRunner().invoke(lint_cli.lint, ["--path", str(bench), "-j", "1"])

    assert result.exit_code == 1
    assert "npm exploded" in result.output
    assert "✗ alpha  tool failed" in _summary(result.output)
    assert "1 of 2 OK" in _summary(result.output)


def test_python_task_runs_pyright_after_ruff(tmp_path, monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(lint_cli, "_run_python", lambda root, fix, r: order.append("ruff"))
    monkeypatch.setattr(lint_cli, "_run_pyright", lambda root, r: order.append("pyright"))

    lint_cli._python_task(tmp_path, True, lint_cli._Report())

    assert order == ["ruff", "pyright"]


# Parsers: samples of what the tools really print


def test_parse_ruff_check(bench):
    stdout = json.dumps(
        [
            {
                "code": "I001",
                "filename": str(bench / "apps/alpha/x.py"),
                "location": {"row": 8, "column": 1},
                "message": "Import block is un-sorted or un-formatted",
                "fix": {"applicability": "safe"},
            }
        ]
    )

    [d] = lint_cli._parse_ruff_check(stdout)

    assert (d.path, d.line, d.col, d.code, d.fixable) == ("apps/alpha/x.py", 8, 1, "I001", True)


def test_parse_ruff_format_reports_each_file_once(bench):
    hunk = {"filename": str(bench / "apps/alpha/x.py"), "location": {"row": 1, "column": 2}}
    later = {**hunk, "location": {"row": 7, "column": 1}}

    [d] = lint_cli._parse_ruff_format(json.dumps([hunk, later]))

    assert (d.path, d.line, d.code, d.fixable) == ("apps/alpha/x.py", 1, "format", True)


def test_parse_pyright_skips_information(bench):
    def entry(severity):
        return {
            "file": str(bench / "apps/alpha/x.py"),
            "severity": severity,
            "message": "msg\n  detail",
            "range": {"start": {"line": 168, "character": 32}},
            "rule": "reportArgumentType",
        }

    stdout = json.dumps({"generalDiagnostics": [entry("error"), entry("information")]})

    [d] = lint_cli._parse_pyright(stdout)

    assert (d.line, d.col, d.severity, d.message) == (169, 33, "error", "msg\n  detail")


def test_parse_tsc_keeps_continuation_lines(bench):
    stdout = (
        "frontend/src/a.vue(12,5): error TS2322: Type 'number' is not assignable to 'string'.\n"
        "  Details about it.\n"
        "frontend/src/b.ts(1,1): error TS6133: 'x' is declared but its value is never read.\n"
    )

    first, second = lint_cli._tsc_parser(bench / "apps/alpha")(stdout)

    assert (first.path, first.line, first.col, first.code) == (
        "apps/alpha/frontend/src/a.vue",
        12,
        5,
        "TS2322",
    )
    assert first.message.endswith("\n  Details about it.")
    assert second.path == "apps/alpha/frontend/src/b.ts"


def test_unparsable_failure_keeps_raw_output():
    report = lint_cli._Report()
    proc = subprocess.CompletedProcess([], 3, stdout="", stderr="Config error")

    lint_cli._collect(report, "pyright", proc, lint_cli._parse_pyright)

    assert report.ok is False
    assert report.diagnostics == []
    assert report.raw == ["pyright exited with code 3\nConfig error"]
