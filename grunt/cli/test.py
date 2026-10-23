import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

lazy from grunt.apps.manifest import is_app
lazy from grunt.cli.changed_tests import changed_files, select
lazy from grunt.site.manager import site_manager

# pytest-xdist; a file stays on one worker, so tests sharing state within a
# file keep their order.
PARALLEL = ["-n", "auto", "--dist", "loadfile"]
PARALLEL_FROM_FILES = 8


@click.command("test", context_settings={"ignore_unknown_options": True})
@click.argument("app", required=False)
@click.option("--doctype", help="Name of the DocType to test")
@click.option("--site", help="Site to run tests for")
@click.option(
    "--changed",
    is_flag=True,
    help="Only what the uncommitted changes can break (ruff, pytest, vitest related)",
)
@click.option(
    "--base", default="HEAD", show_default=True, help="With --changed: compare to this ref"
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test(
    app: str | None = None,
    doctype: str | None = None,
    site: str | None = None,
    changed: bool = False,
    base: str = "HEAD",
    pytest_args: tuple[str, ...] = (),
):
    """Run tests for the framework, specific app, or DocType.

    The full suite runs in CI (GitHub Actions); locally use --changed.
    """

    # If app starts with '-', treat it as a pytest arg
    if app and app.startswith("-"):
        pytest_args = (app, *pytest_args)
        app = None

    if changed:
        repo = site_manager.bench_dir / "apps" / (app or "grunt")
        sys.exit(_run_changed(repo, base, pytest_args))

    apps_dir = site_manager.bench_dir / "apps"
    if app:
        if not (apps_dir / app).is_dir():
            click.echo(f"Error: App '{app}' not found at {apps_dir / app}", err=True)
            raise SystemExit(1)
        roots = [apps_dir / app]
    else:
        roots = [apps_dir / "grunt"] + sorted(
            d for d in apps_dir.iterdir() if d.is_dir() and d.name != "grunt" and is_app(d)
        )

    # One pytest session per app: each app's tests/conftest.py builds the same
    # fixtures (grunt.testkit.make_app_fixtures) and points the shared FastAPI
    # app at its own database - in one session the last conftest would win.
    runs = [(root, paths) for root in roots if (paths := _test_paths(root, doctype))]
    if not runs:
        if doctype:
            click.echo(f"No tests found for DocType '{doctype}'")
        elif app:
            click.echo(f"No tests found for app '{app}'")
        else:
            click.echo("No tests found.")
        return

    if site:
        os.environ["GRUNT_SITE"] = site

    # Run pytest via subprocess so the correct project venv is used

    venv_pytest = site_manager.bench_dir / ".venv" / "bin" / "pytest"
    pytest_bin = str(venv_pytest) if venv_pytest.exists() else shutil.which("pytest") or ""
    if not pytest_bin:
        click.echo(
            click.style("[error] pytest not found. Install it: pip install pytest", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    results: list[tuple[str, int]] = []
    for root, paths in runs:
        targets = [str(p.relative_to(root)) for p in paths if p != root]
        cmd = [pytest_bin, *targets, *pytest_args]
        if "-v" not in cmd and "-q" not in cmd:
            cmd.append("-v")
        if len(runs) > 1:
            click.echo(click.style(f"\n▶ {root.name}", bold=True))
        else:
            click.echo(f"Running tests for: {', '.join(map(str, paths))}")
        # The app's own directory anchors pytest: its conftest and pyproject.
        results.append((root.name, subprocess.run(cmd, cwd=str(root)).returncode))

    if len(results) > 1:
        click.echo(click.style("\nSummary", bold=True))
        for name, code in results:
            mark = click.style("✓", fg="green") if code == 0 else click.style("✗", fg="red")
            click.echo(f"  {mark} {name}")
    sys.exit(max(code for _, code in results))


def _test_paths(root: Path, doctype: str | None) -> list[Path]:
    """What to run in one app (or the framework): with *doctype*, that
    DocType's tests; otherwise ``[root]`` when it has any tests at all -
    pytest then collects them itself (``testpaths``, ``norecursedirs``)."""
    if not doctype:
        has_tests = any(
            not any(part in _SKIP_DIRS for part in f.relative_to(root).parts)
            for f in root.rglob("test_*.py")
        )
        return [root] if has_tests else []
    paths: list[Path] = []
    for dt_dir in root.rglob("doctypes"):
        if not dt_dir.is_dir() or any(part in _SKIP_DIRS for part in dt_dir.parts):
            continue
        # Try both original name and snake_case/lowercase
        for cand in (doctype, doctype.lower(), doctype.replace(" ", "_").lower()):
            if (dt_dir / cand).is_dir():
                _add_tests_from_dir(dt_dir / cand, paths)
                break
    return paths


_SKIP_DIRS = {"node_modules", ".venv", "venv", "dist", ".git"}


def _add_tests_from_dir(dt_dir: Path, test_paths: list[Path]):
    """Find tests in a DocType directory."""
    # Look for tests/ folder
    if (dt_dir / "tests").is_dir():
        test_paths.append(dt_dir / "tests")

    # Look for test_*.py files in the DocType dir itself
    test_paths.extend(sorted(dt_dir.glob("test_*.py")))


def _run_changed(repo: Path, base: str, pytest_args: tuple[str, ...]) -> int:

    if not (repo / ".git").exists():
        click.echo(f"Error: {repo} is not a git repository", err=True)
        return 1
    files = changed_files(repo, base)
    if not files:
        click.echo(f"No changes against {base}.")
        return 0
    sel = select(repo, files)

    def run(title: str, cmd: list[str]) -> int:
        click.echo(click.style(f"\n▶ {title}", bold=True))
        return subprocess.run(cmd, cwd=str(repo)).returncode

    def rel(paths) -> list[str]:
        return sorted(str(p.relative_to(repo)) for p in paths)

    codes: list[int] = []
    if sel.python:
        codes.append(run("ruff", [sys.executable, "-m", "ruff", "check", *rel(sel.python)]))
    pytest = [sys.executable, "-m", "pytest", "-q"]
    if sel.full:
        codes.append(run(f"pytest: all ({sel.full} changed)", [*pytest, *PARALLEL, *pytest_args]))
    elif sel.tests:
        tests = rel(sel.tests)
        # Starting workers costs a few seconds - only worth it for a bigger batch.
        parallel = PARALLEL if len(tests) >= PARALLEL_FROM_FILES else []
        codes.append(run(f"pytest: {len(tests)} files", [*pytest, *parallel, *tests, *pytest_args]))
    if sel.frontend and (npx := shutil.which("npx")):
        codes.append(
            run(
                "vitest related",
                [npx, "vitest", "related", "--run", "--passWithNoTests", *rel(sel.frontend)],
            )
        )

    if sel.uncovered and not sel.full:
        click.echo(click.style("\nNo tests name these changes (CI runs everything):", fg="yellow"))
        for name in rel(sel.uncovered):
            click.echo(f"  {name}")
    return max(codes, default=0)
