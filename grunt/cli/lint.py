from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

# ── Discovery helpers ─────────────────────────────────────────────────────────


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


# ── Linters ───────────────────────────────────────────────────────────────────


def _print_status(name: str, ok: bool) -> None:
    if ok:
        click.echo(click.style(f"  ✓ {name}: OK\n", fg="green"))
    else:
        click.echo(click.style(f"  ✗ {name}: errors found\n", fg="red"))


def _run_python(root: Path, fix: bool) -> int:
    if shutil.which("ruff") is None:
        click.echo(click.style("  [skip] ruff is not installed", fg="yellow"))
        return 0

    results = []

    click.echo(click.style("── ruff check ──", bold=True))
    cmd = ["ruff", "check", "."]
    if fix:
        cmd.append("--fix")
    results.append(subprocess.run(cmd, cwd=root).returncode)

    click.echo(click.style("── ruff format ──", bold=True))
    cmd = ["ruff", "format", "."]
    if not fix:
        cmd.append("--check")
    results.append(subprocess.run(cmd, cwd=root).returncode)

    ok = all(r == 0 for r in results)
    _print_status("Python (ruff)", ok)
    return 0 if ok else 1


def _run_frontend(root: Path) -> int:
    if not (root / "package.json").exists():
        click.echo(click.style("  [skip] package.json not found", fg="yellow"))
        return 0

    if shutil.which("npm") is None:
        click.echo(click.style("  [skip] npm not found", fg="yellow"))
        return 0

    click.echo(click.style("── vue-tsc ──", bold=True))
    pm = (
        "pnpm"
        if (root / "pnpm-lock.yaml").exists()
        else "yarn"
        if (root / "yarn.lock").exists()
        else "npm"
    )
    result = subprocess.run([pm, "run", "typecheck"], cwd=root)
    ok = result.returncode == 0
    _print_status("TypeScript/Vue (vue-tsc)", ok)
    return result.returncode


def _lint_app(app_root: Path, fix: bool, only_py: bool, only_js: bool) -> int:
    """Run lint for a single app. Returns 0 on success, 1 on failure."""
    codes: list[int] = []
    if not only_js:
        codes.append(_run_python(app_root, fix))
    if not only_py:
        codes.append(_run_frontend(app_root))
    return 1 if any(c != 0 for c in codes) else 0


# ── Modes ─────────────────────────────────────────────────────────────────────


def _run_single(root: Path, fix: bool, only_py: bool, only_js: bool) -> None:
    click.echo(f"Project: {root}\n")
    code = _lint_app(root, fix, only_py, only_js)
    if code != 0:
        click.echo(click.style("Errors found.", fg="red", bold=True))
        raise SystemExit(1)
    click.echo(click.style("All good.", fg="green", bold=True))


def _run_bench(
    bench_root: Path,
    selected: tuple[str, ...],
    fix: bool,
    only_py: bool,
    only_js: bool,
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

    click.echo(f"Bench: {bench_root}")
    click.echo(f"Apps: {', '.join(a.name for a in target)}\n")

    results: dict[str, int] = {}
    for app_root in target:
        click.echo(click.style(f"{'─' * 6} {app_root.name} {'─' * 30}", bold=True, fg="cyan"))
        results[app_root.name] = _lint_app(app_root, fix, only_py, only_js)

    click.echo(click.style("─" * 40, bold=True))
    click.echo(click.style("Summary:", bold=True))
    all_ok = True
    for app_name, code in results.items():
        ok = code == 0
        all_ok = all_ok and ok
        status = click.style("✓ OK", fg="green") if ok else click.style("✗ errors", fg="red")
        click.echo(f"  {app_name}: {status}")

    click.echo()
    if not all_ok:
        click.echo(click.style("Errors found.", fg="red", bold=True))
        raise SystemExit(1)
    click.echo(click.style("All good.", fg="green", bold=True))


# ── Command ───────────────────────────────────────────────────────────────────


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
def lint(fix: bool, only_py: bool, only_js: bool, path: str | None, apps: tuple[str, ...]) -> None:
    """Check the code: ruff (Python) + vue-tsc (TS/Vue).

    From the bench directory, checks all or the selected (--app) apps.
    From an app directory, checks only that app.
    """
    start = Path(path).resolve() if path else Path.cwd()

    if _is_bench_root(start):
        _run_bench(start, apps, fix, only_py, only_js)
        return

    if apps:
        # --app вказано поза bench root → знайти bench вгору по дереву
        bench = _find_bench_root(start)
        if bench is None:
            click.echo(
                click.style(
                    "[error] bench root not found (no apps/ with Python packages)", fg="red"
                ),
                err=True,
            )
            raise SystemExit(1)
        _run_bench(bench, apps, fix, only_py, only_js)
        return

    # Single app mode
    root = _find_app_root(start)
    if root is None or not (root / "pyproject.toml").exists():
        click.echo(click.style(f"[error] pyproject.toml not found in: {start}", fg="red"), err=True)
        raise SystemExit(1)
    _run_single(root, fix, only_py, only_js)
