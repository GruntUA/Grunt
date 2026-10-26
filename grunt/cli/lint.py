import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click

# apps/grunt: its node_modules ships the pinned pyright
_GRUNT_ROOT = Path(__file__).parents[2]

# Discovery helpers


def _is_bench_root(path: Path) -> bool:
    """True if path looks like a bench root (has apps/ with ≥1 Python package)."""
    apps_dir = path / "apps"
    return apps_dir.is_dir() and any(
        (d / "pyproject.toml").exists() for d in apps_dir.iterdir() if d.is_dir()
    )


def _find_bench_root(start: Path) -> Path | None:
    """Walk up from start to find a bench root."""
    for directory in [start.resolve(), *start.resolve().parents]:
        if _is_bench_root(directory):
            return directory
    return None


def _find_app_root(start: Path) -> Path | None:
    """Walk up from start to find the nearest directory with pyproject.toml."""
    for directory in [start.resolve(), *start.resolve().parents]:
        if (directory / "pyproject.toml").exists():
            return directory
    return None


def _discover_apps(bench_root: Path) -> list[Path]:
    """Return all app directories inside bench_root/apps/ that have pyproject.toml."""
    apps_dir = bench_root / "apps"
    return sorted(d for d in apps_dir.iterdir() if d.is_dir() and (d / "pyproject.toml").exists())


# Results
#
# Every tool runs in a machine-readable mode and its findings are normalised to
# Diagnostic, so the report looks the same whichever tool found the problem.


@dataclass
class Diagnostic:
    tool: str
    path: str  # relative to cwd when possible: clickable in the terminal, short for an LLM
    line: int  # 1-based
    col: int  # 1-based
    severity: str  # error | warning
    code: str
    message: str
    fixable: bool = False


@dataclass
class _Report:
    """What one task found; filled from a worker thread, rendered by the main one."""

    ok: bool = True
    diagnostics: list[Diagnostic] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # skipped steps
    raw: list[str] = field(default_factory=list)  # output of tools that failed unparsed


def _rel(path: str | Path) -> str:
    rel = os.path.relpath(path)
    return str(path) if rel.startswith("..") else rel


def _exec(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=root, capture_output=True, text=True)


def _collect(
    report: _Report,
    tool: str,
    proc: subprocess.CompletedProcess[str],
    parse: Callable[[str], list[Diagnostic]],
) -> None:
    """Add parsed diagnostics; fall back to the raw output if the tool failed without any."""
    try:
        diagnostics = parse(proc.stdout)
    except ValueError, KeyError, TypeError:
        diagnostics = None
    if proc.returncode != 0:
        report.ok = False
    if diagnostics is None or (proc.returncode != 0 and not diagnostics):
        output = (proc.stdout + proc.stderr).strip()
        report.raw.append(f"{tool} exited with code {proc.returncode}\n{output}".rstrip())
    else:
        report.diagnostics.extend(diagnostics)


# Linters


def _parse_ruff_check(stdout: str) -> list[Diagnostic]:
    return [
        Diagnostic(
            tool="ruff",
            path=_rel(d["filename"]),
            line=d["location"]["row"],
            col=d["location"]["column"],
            severity="error",
            code=d["code"] or "syntax",
            message=d["message"],
            fixable=bool(d.get("fix")) and d["fix"]["applicability"] == "safe",
        )
        for d in json.loads(stdout)
    ]


def _parse_ruff_format(stdout: str) -> list[Diagnostic]:
    # ruff reports every changed hunk; one entry per file is enough
    first: dict[str, dict] = {}
    for d in json.loads(stdout):
        first.setdefault(d["filename"], d)
    return [
        Diagnostic(
            tool="ruff-format",
            path=_rel(name),
            line=d["location"]["row"],
            col=d["location"]["column"],
            severity="error",
            code="format",
            message="File is not formatted",
            fixable=True,
        )
        for name, d in first.items()
    ]


def _run_python(root: Path, fix: bool, report: _Report) -> None:
    # Run from the interpreter's own venv: `grunt` delegates here without .venv/bin on PATH.
    if importlib.util.find_spec("ruff") is None:
        report.notes.append("ruff is not installed")
        return

    ruff = [sys.executable, "-m", "ruff"]
    cmd = [*ruff, "check", "--output-format", "json", "."]
    if fix:
        cmd.append("--fix")
    _collect(report, "ruff check", _exec(cmd, root), _parse_ruff_check)

    if fix:
        _collect(report, "ruff format", _exec([*ruff, "format", "."], root), lambda _: [])
    else:
        cmd = [*ruff, "format", "--check", "--output-format", "json", "."]
        _collect(report, "ruff format", _exec(cmd, root), _parse_ruff_format)


def _has_pyright_config(root: Path) -> bool:
    if (root / "pyrightconfig.json").exists():
        return True
    pyproject = root / "pyproject.toml"
    return pyproject.exists() and "[tool.pyright]" in pyproject.read_text()


def _pyright_cmd() -> list[str] | None:
    """Pinned pyright from grunt's node_modules, else a global one, else npx."""
    local = _GRUNT_ROOT / "node_modules" / ".bin" / "pyright"
    if local.exists():
        return [str(local)]
    if shutil.which("pyright"):
        return ["pyright"]
    if shutil.which("npx"):
        return ["npx", "--yes", "pyright"]
    return None


def _parse_pyright(stdout: str) -> list[Diagnostic]:
    return [
        Diagnostic(
            tool="pyright",
            path=_rel(d["file"]),
            line=d["range"]["start"]["line"] + 1,
            col=d["range"]["start"]["character"] + 1,
            severity=d["severity"],
            code=d.get("rule", ""),
            message=d["message"],
        )
        for d in json.loads(stdout)["generalDiagnostics"]
        if d["severity"] in ("error", "warning")
    ]


def _run_pyright(root: Path, report: _Report) -> None:
    """The type checker behind Pylance; only for apps that ship a pyright config."""
    if not _has_pyright_config(root):
        report.notes.append("pyright config not found")
        return

    cmd = _pyright_cmd()
    if cmd is None:
        report.notes.append("pyright/npx not found")
        return

    _collect(report, "pyright", _exec([*cmd, "--outputjson"], root), _parse_pyright)


# path(line,col): error TS2322: message — continuation lines are indented
_TSC_LINE = re.compile(r"^(.+?)\((\d+),(\d+)\): (error|warning) (TS\d+): (.*)$")


def _tsc_parser(root: Path) -> Callable[[str], list[Diagnostic]]:
    def parse(stdout: str) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for line in stdout.splitlines():
            if m := _TSC_LINE.match(line):
                path, row, col, severity, code, message = m.groups()
                diagnostics.append(
                    Diagnostic(
                        tool="vue-tsc",
                        path=_rel(root / path),
                        line=int(row),
                        col=int(col),
                        severity=severity,
                        code=code,
                        message=message,
                    )
                )
            elif line.startswith(" ") and diagnostics:
                diagnostics[-1].message += "\n" + line.rstrip()
        return diagnostics

    return parse


def _run_frontend(root: Path, report: _Report) -> None:
    if not (root / "package.json").exists():
        report.notes.append("package.json not found")
        return

    if shutil.which("npm") is None:
        report.notes.append("npm not found")
        return

    if (root / "pnpm-lock.yaml").exists():
        cmd = ["pnpm", "--silent", "run", "typecheck", "--pretty", "false"]
    elif (root / "yarn.lock").exists():
        cmd = ["yarn", "--silent", "run", "typecheck", "--pretty", "false"]
    else:
        cmd = ["npm", "run", "--silent", "typecheck", "--", "--pretty", "false"]
    _collect(report, "vue-tsc", _exec(cmd, root), _tsc_parser(root))


def _python_task(root: Path, fix: bool, report: _Report) -> None:
    # Sequential on purpose: with --fix, pyright must see the files ruff rewrote.
    _run_python(root, fix, report)
    _run_pyright(root, report)


# Tasks


@dataclass
class _Task:
    app: str
    label: str
    run: Callable[[_Report], None]


@dataclass
class _TaskResult:
    app: str
    label: str
    duration: float
    report: _Report


def _app_tasks(
    app_root: Path, fix: bool, only_py: bool, only_js: bool, explicit: bool
) -> list[_Task]:
    """Independent units of work for one app: Python (ruff → pyright) and frontend.

    An app without package.json gets no frontend task unless the user asked for
    this app/--js explicitly — otherwise the report fills up with "skipped".
    """
    name = app_root.name
    tasks = []
    if not only_js:
        tasks.append(_Task(name, "Python", lambda r: _python_task(app_root, fix, r)))
    if not only_py and ((app_root / "package.json").exists() or explicit or only_js):
        tasks.append(_Task(name, "Frontend", lambda r: _run_frontend(app_root, r)))
    return tasks


def _run_tasks(
    tasks: list[_Task], jobs: int, on_done: Callable[[_TaskResult], None]
) -> list[_TaskResult]:
    """Run tasks in parallel; on_done is called in the main thread as each one finishes."""

    def run(task: _Task) -> _TaskResult:
        report = _Report()
        started = time.monotonic()
        try:
            task.run(report)
        except Exception as exc:  # a crashed linter fails the app, it must not kill the run
            report.ok = False
            report.raw.append(f"{task.label} crashed: {exc!r}")
        return _TaskResult(task.app, task.label, time.monotonic() - started, report)

    results = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for future in as_completed([pool.submit(run, t) for t in tasks]):
            result = future.result()
            on_done(result)
            results.append(result)
    return results


# Rendering


def _counts(diagnostics: list[Diagnostic]) -> str:
    by_severity = Counter(d.severity for d in diagnostics)
    parts = [f"{n} {sev}{'s' if n > 1 else ''}" for sev, n in sorted(by_severity.items())]
    by_tool = Counter(d.tool for d in diagnostics)
    tools = ", ".join(f"{tool} {n}" for tool, n in sorted(by_tool.items()))
    return f"{', '.join(parts)} ({tools})" if parts else ""


def _echo_progress(result: _TaskResult, show_app: bool) -> None:
    report = result.report
    title = f"{result.app} · {result.label}" if show_app else result.label
    if not report.ok:
        mark = click.style("✗", fg="red")
    elif report.notes and not report.diagnostics:
        mark = click.style("–", fg="yellow")
    else:
        mark = click.style("✓", fg="green")
    details = _counts(report.diagnostics)
    if report.notes:
        details = "; ".join([details, *(f"skipped: {n}" for n in report.notes)]).lstrip("; ")
    if report.raw and not report.diagnostics:
        details = (details + "; " if details else "") + "tool failed, see output below"
    line = f"  {mark} {title:<28} {result.duration:5.1f}s"
    click.echo(f"{line}  {click.style(details, dim=report.ok)}" if details else line)


def _echo_diagnostic(d: Diagnostic) -> None:
    color = "red" if d.severity == "error" else "yellow"
    location = click.style(f"{d.path}:{d.line}:{d.col}:", bold=True)
    tag = f"[{d.tool} {d.code}{', fixable' if d.fixable else ''}]".replace(" ]", "]")
    first, *rest = d.message.splitlines() or [""]
    click.echo(
        f"{location} {click.style(d.severity, fg=color)} {click.style(tag, dim=True)} {first}"
    )
    for line in rest:
        click.echo(f"  {line.rstrip()}")


def _echo_report(results: list[_TaskResult], order: list[str], show_app: bool) -> None:
    """Problems grouped by app (in bench order), then raw output of tools that broke."""
    for app in order:
        app_results = [r for r in results if r.app == app]
        diagnostics = sorted(
            (d for r in app_results for d in r.report.diagnostics),
            key=lambda d: (d.path, d.line, d.col),
        )
        raw = [text for r in app_results for text in r.report.raw]
        if not diagnostics and not raw:
            continue
        click.echo()
        if show_app:
            click.echo(click.style(f"── {app} ── {_counts(diagnostics)}".rstrip(), bold=True))
        for d in diagnostics:
            _echo_diagnostic(d)
        for text in raw:
            click.echo(click.style(text, fg="red"))


def _echo_summary(results: list[_TaskResult], order: list[str], elapsed: float, fix: bool) -> bool:
    failed = [app for app in order if any(not r.report.ok for r in results if r.app == app)]
    diagnostics = [d for r in results for d in r.report.diagnostics]

    click.echo()
    click.echo(click.style(f"Summary ({elapsed:.1f}s):", bold=True))
    width = max((len(app) for app in failed), default=0)
    for app in failed:
        app_diags = [d for r in results if r.app == app for d in r.report.diagnostics]
        counts = _counts(app_diags) or "tool failed"
        click.echo(f"  {click.style('✗', fg='red')} {app:<{width}}  {counts}")
    passed = len(order) - len(failed)
    if passed:
        click.echo(f"  {click.style('✓', fg='green')} {passed} of {len(order)} OK")

    fixable = sum(d.fixable for d in diagnostics)
    if fixable and not fix:
        click.echo(f"  {fixable} fixable with `grunt lint --fix`")

    click.echo()
    if failed:
        click.echo(click.style("Errors found.", fg="red", bold=True))
        return False
    click.echo(click.style("All good.", fg="green", bold=True))
    return True


def _json_report(results: list[_TaskResult], order: list[str], elapsed: float) -> dict:
    apps = []
    for app in order:
        app_results = [r for r in results if r.app == app]
        tasks = [
            {
                "label": r.label,
                "ok": r.report.ok,
                "duration": round(r.duration, 2),
                "skipped": r.report.notes,
                "raw_output": r.report.raw,
            }
            for r in sorted(app_results, key=lambda r: r.label)
        ]
        apps.append({"name": app, "ok": all(t["ok"] for t in tasks), "tasks": tasks})
    diagnostics = [
        {"app": r.app, **asdict(d)}
        for r in results
        for d in sorted(r.report.diagnostics, key=lambda d: (d.path, d.line, d.col))
    ]
    diagnostics.sort(key=lambda d: order.index(d["app"]))
    return {
        "ok": all(a["ok"] for a in apps),
        "duration": round(elapsed, 2),
        "apps": apps,
        "diagnostics": diagnostics,
    }


def _lint(apps: list[Path], fix: bool, only_py: bool, only_js: bool, opts: dict) -> None:
    """Run lint over apps and print the report; exits 1 on errors."""
    as_json = opts["format"] == "json"
    show_app = opts["bench"]
    order = [a.name for a in apps]
    tasks = [
        t for a in apps for t in _app_tasks(a, fix, only_py, only_js, explicit=opts["explicit"])
    ]

    started = time.monotonic()
    on_done = (lambda _: None) if as_json else (lambda r: _echo_progress(r, show_app))
    results = _run_tasks(tasks, opts["jobs"], on_done)
    elapsed = time.monotonic() - started

    if as_json:
        report = _json_report(results, order, elapsed)
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
        ok = report["ok"]
    else:
        _echo_report(results, order, show_app)
        ok = _echo_summary(results, order, elapsed, fix)
    if not ok:
        raise SystemExit(1)


# Modes


def _run_single(root: Path, fix: bool, only_py: bool, only_js: bool, opts: dict) -> None:
    if opts["format"] == "text":
        click.echo(f"Project: {root}\n")
    _lint([root], fix, only_py, only_js, {**opts, "bench": False, "explicit": True})


def _run_bench(
    bench_root: Path,
    selected: tuple[str, ...],
    fix: bool,
    only_py: bool,
    only_js: bool,
    opts: dict,
) -> None:
    all_apps = _discover_apps(bench_root)

    if selected:
        apps_map = {a.name: a for a in all_apps}
        unknown = [a for a in selected if a not in apps_map]
        if unknown:
            available = ", ".join(sorted(apps_map))
            click.echo(
                click.style(
                    f"[error] Unknown apps: {', '.join(unknown)}. Available: {available}",
                    fg="red",
                ),
                err=True,
            )
            raise SystemExit(1)
        target = [apps_map[a] for a in selected]
    else:
        target = all_apps

    if opts["format"] == "text":
        click.echo(f"Bench: {bench_root}")
        click.echo(f"Apps: {', '.join(a.name for a in target)}\n")

    _lint(target, fix, only_py, only_js, {**opts, "bench": True, "explicit": bool(selected)})


# Command


@click.command("lint")
@click.option("--fix", is_flag=True, help="Fix automatically (ruff --fix + ruff format)")
@click.option("--py", "only_py", is_flag=True, help="Python only")
@click.option("--js", "only_js", is_flag=True, help="TypeScript/Vue only")
@click.option("--path", default=None, help="Project or bench root (auto-detected by default)")
@click.option(
    "--app",
    "apps",
    multiple=True,
    metavar="APP",
    help="App to check (repeatable). Enables bench mode.",
)
@click.option(
    "-j",
    "--jobs",
    type=click.IntRange(min=1),
    default=lambda: os.cpu_count() or 1,
    show_default="CPU count",
    help="Linters to run in parallel",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="json: one machine-readable document on stdout",
)
def lint(
    fix: bool,
    only_py: bool,
    only_js: bool,
    path: str | None,
    apps: tuple[str, ...],
    jobs: int,
    output_format: str,
) -> None:
    """Check the code: ruff + pyright (Python) + vue-tsc (TS/Vue).

    From the bench directory, checks all or the selected (--app) apps.
    From an app directory, checks only that app.
    Linters run in parallel (-j). Problems are printed as
    `path:line:col: severity [tool code] message`, grouped by app.
    """
    start = Path(path).resolve() if path else Path.cwd()
    opts = {"jobs": jobs, "format": output_format}

    if _is_bench_root(start):
        _run_bench(start, apps, fix, only_py, only_js, opts)
        return

    if apps:
        # app вказано поза bench root -> знайти bench вгору по дереву
        bench = _find_bench_root(start)
        if bench is None:
            click.echo(
                click.style(
                    "[error] bench root not found (no apps/ with Python packages)", fg="red"
                ),
                err=True,
            )
            raise SystemExit(1)
        _run_bench(bench, apps, fix, only_py, only_js, opts)
        return

    # Single app mode
    root = _find_app_root(start)
    if root is None or not (root / "pyproject.toml").exists():
        click.echo(click.style(f"[error] pyproject.toml not found in: {start}", fg="red"), err=True)
        raise SystemExit(1)
    _run_single(root, fix, only_py, only_js, opts)
