from __future__ import annotations

import sys
from pathlib import Path  # noqa: TC003

import click


@click.command("test", context_settings={"ignore_unknown_options": True})
@click.argument("app", required=False)
@click.option("--doctype", help="Name of the DocType to test")
@click.option("--site", help="Site to run tests for")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test(
    app: str | None = None,
    doctype: str | None = None,
    site: str | None = None,
    pytest_args: tuple[str, ...] = (),
):
    """Run tests for the framework, specific app, or DocType."""
    from grunt.site.manager import site_manager

    # If app starts with '-', treat it as a pytest arg
    if app and app.startswith("-"):
        pytest_args = (app, *pytest_args)
        app = None

    # 1. Base test paths
    test_paths = []

    # If no filters, include base framework tests (skip silently if the dir doesn't exist)
    if not app and not doctype:
        base_tests = site_manager.bench_dir / "apps" / "grunt" / "backend" / "tests"
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
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    bench_dir = site_manager.bench_dir
    venv_pytest = bench_dir / ".venv" / "bin" / "pytest"
    if venv_pytest.exists():
        pytest_bin = str(venv_pytest)
    else:
        pytest_bin = shutil.which("pytest") or ""

    if not pytest_bin:
        click.echo(
            click.style("[error] pytest не знайдено. Встановіть: pip install pytest", fg="red"),
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
