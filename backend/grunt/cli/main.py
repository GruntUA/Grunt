"""Ґрунт CLI — project management commands."""

from __future__ import annotations

import os
import secrets
import subprocess
import sys

import click
from rich.console import Console
from rich.table import Table as RichTable

console = Console()


@click.group()
def cli() -> None:
    """Ґрунт — metadata-driven application framework."""


# ── init ──────────────────────────────────────────────────────────────────


@cli.command()
@click.argument("project_name", default=".")
def init(project_name: str) -> None:
    """Ініціалізує новий Ґрунт проєкт."""
    target = os.path.abspath(project_name)

    if project_name != ".":
        os.makedirs(target, exist_ok=True)
        console.print(f"[green]Створено директорію:[/green] {target}")

    env_path = os.path.join(target, ".env")
    example_path = os.path.join(target, ".env.example")

    if not os.path.exists(env_path):
        # Copy from .env.example if available, otherwise create minimal
        if os.path.exists(example_path):
            with open(example_path) as f:
                content = f.read()
        else:
            content = "# Ґрунт configuration\nDATABASE_URL=sqlite+aiosqlite:///./grunt.db\n"

        # Generate and inject secret key
        secret = secrets.token_hex(32)
        if "SECRET_KEY=" in content:
            lines = content.splitlines()
            lines = [
                f"SECRET_KEY={secret}" if line.startswith("SECRET_KEY=") else line
                for line in lines
            ]
            content = "\n".join(lines) + "\n"
        else:
            content += f"SECRET_KEY={secret}\n"

        with open(env_path, "w") as f:
            f.write(content)
        console.print("[green]Створено .env з новим SECRET_KEY[/green]")
    else:
        console.print("[yellow].env вже існує — пропускаємо[/yellow]")

    # Run migrations
    backend_dir = os.path.join(target, "backend")
    if os.path.isdir(backend_dir):
        console.print("[blue]Запускаємо міграції…[/blue]")
        subprocess.run(["alembic", "upgrade", "head"], cwd=backend_dir)

    console.print("\n[bold green]✓ Проєкт ініціалізовано![/bold green]")
    console.print("  Запустіть сервер: [cyan]grunt serve[/cyan]")


# ── serve ─────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8000, type=int, help="Backend port")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on changes")
@click.option("--backend-only", is_flag=True, help="Only start FastAPI")
@click.option("--frontend-only", is_flag=True, help="Only start Vite dev server")
def serve(host: str, port: int, reload: bool, backend_only: bool, frontend_only: bool) -> None:
    """Запускає dev сервери (backend + frontend)."""
    import signal

    procs: list[subprocess.Popen] = []

    def _shutdown(signum, frame):  # noqa: ANN001
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if not frontend_only:
        console.print(f"[green]Запускаємо FastAPI на {host}:{port}…[/green]")
        cmd = [
            sys.executable, "-m", "uvicorn",
            "grunt.main:app",
            "--host", host,
            "--port", str(port),
        ]
        if reload:
            cmd.append("--reload")
        procs.append(subprocess.Popen(cmd, cwd="backend"))

    if not backend_only:
        frontend_dir = "frontend"
        if os.path.isdir(frontend_dir):
            console.print("[green]Запускаємо Vite dev server…[/green]")
            procs.append(subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=frontend_dir,
            ))
        else:
            console.print("[yellow]frontend/ не знайдено — пропускаємо Vite[/yellow]")

    if not procs:
        console.print("[red]Нічого не запущено[/red]")
        return

    # Wait for all processes
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        _shutdown(None, None)


# ── db ────────────────────────────────────────────────────────────────────


@cli.group()
def db() -> None:
    """Команди для управління базою даних."""


@db.command("migrate")
def db_migrate() -> None:
    """Запускає Alembic upgrade head."""
    result = subprocess.run(["alembic", "upgrade", "head"], cwd="backend")
    sys.exit(result.returncode)


@db.command("reset")
@click.confirmation_option(prompt="⚠️  Скинути всі дані? Це незворотньо")
def db_reset() -> None:
    """Скидає БД (тільки при DEBUG=true)."""
    from grunt.config import settings

    if not settings.debug:
        console.print("[red]db reset дозволено тільки при DEBUG=true[/red]")
        sys.exit(1)

    import asyncio

    from grunt.core.db.base import Base
    from grunt.core.db.session import engine

    async def _reset() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())
    console.print("[green]✓ База даних скинута і перестворена[/green]")


# ── doctype ──────────────────────────────────────────────────────────────


@cli.group()
def doctype() -> None:
    """Команди для роботи з DocTypes."""


@doctype.command("list")
def doctype_list() -> None:
    """Виводить список зареєстрованих DocTypes."""
    import httpx

    try:
        # Try to talk to a running server
        resp = httpx.get("http://localhost:8000/api/v1/meta/doctypes")
        if resp.status_code == 401:
            console.print("[red]Потрібна авторизація. Спочатку отримайте токен.[/red]")
            return
        items = resp.json()
    except httpx.ConnectError:
        console.print("[red]Сервер не запущений. Запустіть: grunt serve[/red]")
        return

    table = RichTable(title="DocTypes")
    table.add_column("Name", style="cyan")
    table.add_column("Label")
    table.add_column("Module")
    table.add_column("Child?")

    for item in items:
        table.add_row(
            item["name"],
            item["label"],
            item["module"],
            "✓" if item.get("is_child") else "",
        )

    console.print(table)


@doctype.command("sync")
@click.argument("name")
def doctype_sync(name: str) -> None:
    """Синхронізує DocType з базою даних."""
    import httpx

    try:
        resp = httpx.post(f"http://localhost:8000/api/v1/meta/doctypes/{name}/sync")
        if resp.status_code == 404:
            console.print(f"[red]DocType '{name}' не знайдено[/red]")
            return
        data = resp.json()
        console.print(f"[green]✓ {data.get('message', 'Синхронізовано')}[/green]")
        if data.get("columns_added"):
            console.print(f"  Додані колонки: {', '.join(data['columns_added'])}")
    except httpx.ConnectError:
        console.print("[red]Сервер не запущений. Запустіть: grunt serve[/red]")
