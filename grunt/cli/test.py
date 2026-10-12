from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from pathlib import Path

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
    from grunt.site.manager import site_manager

    # If app starts with '-', treat it as a pytest arg
    if app and app.startswith("-"):
        pytest_args = (app, *pytest_args)
        app = None

    if changed:
        repo = site_manager.bench_dir / "apps" / (app or "grunt")
        sys.exit(_run_changed(repo, base, pytest_args))

    # 1. Base test paths
    test_paths = []

    # If no filters, include base framework tests (skip silently if the dir doesn't exist)
    if not app and not doctype:
        base_tests = site_manager.bench_dir / "apps" / "grunt" / "tests"
        if base_tests.is_dir():
            test_paths.append(str(base_tests))

    # 2. Discover DocType tests
    apps_dir = site_manager.bench_dir / "apps"

    search_dirs = []
    if app:
        app_path = apps_dir / app
        if not app_path.is_dir():
            click.echo(f"Error: App '{app}' not found at {app_path}", err=True)
            raise SystemExit(1)
        search_dirs.append(app_path)
    else:
        # Search all apps
        for item in apps_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                search_dirs.append(item)

    for s_dir in search_dirs:
        for dt_dir in s_dir.rglob("doctypes"):
            if not dt_dir.is_dir():
                continue

            if doctype:
                # Try both original name and snake_case/lowercase
                candidates = [doctype, doctype.lower(), doctype.replace(" ", "_").lower()]
                for cand in candidates:
                    target_dt = dt_dir / cand
                    if target_dt.is_dir():
                        _add_tests_from_dir(target_dt, test_paths)
                        break
            else:
                # Add tests for all doctypes in this directory
                for dt in dt_dir.iterdir():
                    if dt.is_dir() and not dt.name.startswith((".", "_")):
                        _add_tests_from_dir(dt, test_paths)

    if not test_paths:
        if doctype:
            click.echo(f"No tests found for DocType '{doctype}'")
        elif app:
            click.echo(f"No tests found for app '{app}'")
        else:
            click.echo("No tests found.")
        return

    # 3. Handle site context if provided
    # (Optional: set environment variable for site)
    if site:
        import os

        os.environ["GRUNT_SITE"] = site

    # 4. Run pytest via subprocess so the correct project venv is used
    import shutil
    import subprocess

    bench_dir = site_manager.bench_dir
    venv_pytest = bench_dir / ".venv" / "bin" / "pytest"
    pytest_bin = str(venv_pytest) if venv_pytest.exists() else shutil.which("pytest") or ""

    if not pytest_bin:
        click.echo(
            click.style("[error] pytest not found. Install it: pip install pytest", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    # Resolve app root for the app whose conftest/pyproject.toml should anchor pytest.
    # When a single app is targeted use its root; otherwise use the grunt framework root
    # (which has conftest.py and pyproject.toml defining asyncio mode etc.).
    grunt_app_root = bench_dir / "apps" / "grunt"
    if app and (bench_dir / "apps" / app).is_dir():
        pytest_cwd = bench_dir / "apps" / app
    else:
        pytest_cwd = grunt_app_root

    click.echo(f"Running tests for: {', '.join(test_paths)}")
    cmd = [pytest_bin] + test_paths + list(pytest_args)
    if "-v" not in cmd and "-q" not in cmd:
        cmd.append("-v")

    result = subprocess.run(cmd, cwd=str(pytest_cwd))
    sys.exit(result.returncode)


def _add_tests_from_dir(dt_dir: Path, test_paths: list[str]):
    """Find tests in a DocType directory."""
    # Look for tests/ folder
    tests_subdir = dt_dir / "tests"
    if tests_subdir.is_dir():
        test_paths.append(str(tests_subdir))

    # Look for test_*.py files in the DocType dir itself
    for test_file in dt_dir.glob("test_*.py"):
        test_paths.append(str(test_file))


def _run_changed(repo: Path, base: str, pytest_args: tuple[str, ...]) -> int:
    import shutil
    import subprocess

    from grunt.cli.changed_tests import changed_files, select

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
