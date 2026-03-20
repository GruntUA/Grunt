"""grunt db * — управління базою даних."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()

_BACKEND_DIR = Path(__file__).parents[4] / "backend"


@click.group()
def db() -> None:
    """Команди для управління базою даних."""


@db.command("migrate")
def db_migrate() -> None:
    """Застосовує всі міграції (alembic upgrade head)."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(_BACKEND_DIR),
    )
    if result.returncode == 0:
        console.print("[green]✓[/green] Міграції застосовані")
    sys.exit(result.returncode)


@db.command("rollback")
@click.argument("steps", default=1)
def db_rollback(steps: int) -> None:
    """Відкочує N міграцій назад."""
    result = subprocess.run(
        ["alembic", "downgrade", f"-{steps}"],
        cwd=str(_BACKEND_DIR),
    )
    sys.exit(result.returncode)


@db.command("history")
def db_history() -> None:
    """Показує історію міграцій."""
    subprocess.run(
        ["alembic", "history", "--verbose"],
        cwd=str(_BACKEND_DIR),
    )


@db.command("reset")
@click.option("--yes", is_flag=True, help="Пропустити підтвердження")
def db_reset(yes: bool) -> None:
    """⚠️  Скидає всі дані. Тільки при DEBUG=true."""
    from grunt.config import settings  # noqa: PLC0415

    if not settings.debug:
        console.print("[red]✗[/red] db reset дозволено тільки при DEBUG=true")
        sys.exit(1)

    if not yes and not click.confirm(
        "[bold red]⚠️  Всі дані будуть видалені. Продовжити?[/bold red]"
    ):
        console.print("[dim]Скасовано[/dim]")
        return

    import asyncio  # noqa: PLC0415

    async def _reset() -> None:
        from grunt.core.db.base import Base       # noqa: PLC0415
        from grunt.core.db.session import engine  # noqa: PLC0415

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())
    console.print("[green]✓[/green] БД скинута і перестворена")

    # Синхронізуємо alembic_version
    subprocess.run(["alembic", "stamp", "head"], cwd=str(_BACKEND_DIR))
    console.print("[green]✓[/green] Alembic синхронізовано")
