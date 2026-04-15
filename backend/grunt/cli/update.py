"""grunt update — оновити фреймворк та всі додатки."""

from __future__ import annotations

import shutil
import subprocess
import sys

import click


@click.command("update")
@click.option("--skip-migrate", is_flag=True, help="Не запускати grunt migrate після оновлення")
@click.option("--skip-packages", is_flag=True, help="Не оновлювати Python пакети")
@click.option("--skip-npm", is_flag=True, help="Не встановлювати npm пакети")
@click.option("--site", default=None, help="Назва сайту (для migrate)")
def update(skip_migrate: bool, skip_packages: bool, skip_npm: bool, site: str | None) -> None:
    """Оновити фреймворк: пакети + міграція схеми БД.

    Послідовність:

    \b
    1. uv sync --upgrade  (або pip install -U grunt)
    2. npm install
    3. grunt migrate

    Використовуй після оновлення версії Grunt або встановлення нових додатків.
    """
    # ── 1. Оновити Python пакети ──────────────────────────────────────────────
    if not skip_packages:
        click.echo("── [1/3] Оновлення Python пакетів...")
        _run_package_update()
    else:
        click.echo("── [1/3] Оновлення Python пакетів пропущено (--skip-packages)")

    # ── 2. Встановити npm пакети ──────────────────────────────────────────────
    if not skip_npm:
        click.echo("\n── [2/3] Встановлення npm пакетів...")
        _run_npm_install()
    else:
        click.echo("── [2/3] npm install пропущено (--skip-npm)")

    # ── 3. Міграція схеми БД ──────────────────────────────────────────────────
    if not skip_migrate:
        click.echo("\n── [3/3] Міграція схеми БД (grunt migrate)...")
        from grunt.cli.db import db_migrate  # noqa: PLC0415

        ctx = click.Context(db_migrate)
        ctx.invoke(db_migrate, dry_run=False, site=site)
    else:
        click.echo("── [3/3] Міграція пропущена (--skip-migrate)")

    click.echo("\nОновлення завершено.")


def _grunt_app_dir() -> "Path":
    """Return the grunt app root (where pyproject.toml and package.json live)."""
    from pathlib import Path  # noqa: PLC0415

    # update.py lives at apps/grunt/backend/grunt/cli/update.py
    # → 4 levels up = apps/grunt/
    return Path(__file__).resolve().parent.parent.parent.parent


def _run_npm_install() -> None:
    """Run npm install in the grunt app root (where package.json lives)."""
    npm = shutil.which("npm")
    if not npm:
        click.echo("  [warn] npm не знайдено, пропускаю встановлення npm пакетів", err=True)
        return

    result = subprocess.run([npm, "install"], cwd=_grunt_app_dir(), check=False)
    if result.returncode != 0:
        click.echo("  [warn] npm install завершився з помилкою", err=True)


def _run_package_update() -> None:
    """Run the best available package manager to upgrade dependencies."""
    app_dir = _grunt_app_dir()

    # uv (preferred)
    if shutil.which("uv"):
        result = subprocess.run(["uv", "sync", "--upgrade"], cwd=app_dir, check=False)
        if result.returncode != 0:
            click.echo("  [warn] uv sync --upgrade завершився з помилкою", err=True)
        return

    # pip fallback
    click.echo("  uv не знайдено, використовую pip...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "grunt"],
        cwd=app_dir,
        check=False,
    )
    if result.returncode != 0:
        click.echo("  [warn] pip install --upgrade завершився з помилкою", err=True)
