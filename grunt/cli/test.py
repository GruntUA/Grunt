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

    # If no filters, include base tests
    if not app and not doctype:
        test_paths.append(str(site_manager.bench_dir / "apps" / "grunt" / "backend" / "tests"))

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

    # 4. Run pytest
    import pytest  # noqa: PLC0415

    click.echo(f"Running tests for: {', '.join(test_paths)}")
    args = test_paths + list(pytest_args)
    if "-v" not in args and "-q" not in args:
        args.append("-v")

    retcode = pytest.main(args)
    sys.exit(retcode)


def _add_tests_from_dir(dt_dir: Path, test_paths: list[str]):
    """Find tests in a DocType directory."""
    # Look for tests/ folder
    tests_subdir = dt_dir / "tests"
    if tests_subdir.is_dir():
        test_paths.append(str(tests_subdir))

    # Look for test_*.py files in the DocType dir itself
    for test_file in dt_dir.glob("test_*.py"):
        test_paths.append(str(test_file))
