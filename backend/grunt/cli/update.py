"""grunt update — оновити фреймворк та всі додатки."""

from __future__ import annotations

import shutil
import subprocess
import sys

import click


@click.command("update")
@click.option("--skip-migrate", is_flag=True, help="Не запускати grunt migrate після оновлення")
@click.option("--skip-packages", is_flag=True, help="Не оновлювати Python пакети")
@click.option("--site", default=None, help="Назва сайту (для migrate)")
def update(skip_migrate: bool, skip_packages: bool, site: str | None) -> None:
    """Оновити фреймворк: пакети + міграція схеми БД.

    Послідовність:

    \b
    1. uv sync --upgrade  (або pip install -U grunt)
    2. grunt migrate

    Використовуй після оновлення версії Grunt або встановлення нових додатків.
    """
    # ── 1. Оновити Python пакети ──────────────────────────────────────────────
    if not skip_packages:
        click.echo("── [1/2] Оновлення пакетів...")
        _run_package_update()
    else:
        click.echo("── [1/2] Оновлення пакетів пропущено (--skip-packages)")

    # ── 2. Міграція схеми БД ──────────────────────────────────────────────────
    if not skip_migrate:
        click.echo("\n── [2/2] Міграція схеми БД (grunt migrate)...")
        from grunt.cli.db import db_migrate  # noqa: PLC0415

        ctx = click.Context(db_migrate)
        ctx.invoke(db_migrate, dry_run=False, site=site)
    else:
        click.echo("── [2/2] Міграція пропущена (--skip-migrate)")

    click.echo("\nОновлення завершено.")


def _run_package_update() -> None:
    """Run the best available package manager to upgrade dependencies."""
    # uv (preferred)
    if shutil.which("uv"):
        result = subprocess.run(["uv", "sync", "--upgrade"], check=False)
        if result.returncode != 0:
            click.echo("  [warn] uv sync --upgrade завершився з помилкою", err=True)
        return

    # pip fallback
    click.echo("  uv не знайдено, використовую pip...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "grunt"],
        check=False,
    )
    if result.returncode != 0:
        click.echo("  [warn] pip install --upgrade завершився з помилкою", err=True)
