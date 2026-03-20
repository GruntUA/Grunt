"""grunt init — ініціалізація проєкту."""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("project_name", default=".")
def init(project_name: str) -> None:
    """Ініціалізує новий Ґрунт проєкт."""
    cwd = Path.cwd() if project_name == "." else Path(project_name)

    # 1. Створи директорію якщо потрібно
    if project_name != ".":
        cwd.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Створено директорію {project_name}")

    # 2. .env з .env.example
    env_file = cwd / ".env"
    env_example = Path(__file__).parents[4] / ".env.example"

    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
        else:
            env_file.write_text(
                "DEBUG=true\n"
                "DATABASE_URL=sqlite+aiosqlite:///./grunt.db\n"
            )
        console.print("[green]✓[/green] Створено .env")
    else:
        console.print("[yellow]~[/yellow] .env вже існує, пропущено")

    # 3. Генерація SECRET_KEY
    env_content = env_file.read_text()
    if "change-me" in env_content or "SECRET_KEY=" not in env_content:
        secret = secrets.token_hex(32)
        if "SECRET_KEY=" in env_content:
            env_content = re.sub(r"SECRET_KEY=.*", f"SECRET_KEY={secret}", env_content)
        else:
            env_content += f"\nSECRET_KEY={secret}\n"
        env_file.write_text(env_content)
        console.print("[green]✓[/green] SECRET_KEY згенеровано")

    # 4. Alembic міграції
    backend_dir = Path(__file__).parents[4] / "backend"
    console.print("\n[dim]Застосовую міграції...[/dim]")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(backend_dir),
    )
    if result.returncode == 0:
        console.print("[green]✓[/green] Таблиці БД створені")
    else:
        console.print(f"[red]✗[/red] Помилка міграцій:\n{result.stderr}")
        console.print("[dim]Запусти вручну: cd backend && alembic upgrade head[/dim]")

    # 5. Створення адміністратора
    console.print()
    if click.confirm("Створити адміністратора?", default=True):
        email = click.prompt("  Email", default="admin@grunt.local")
        password = click.prompt("  Пароль", hide_input=True, confirmation_prompt=True)
        full_name = click.prompt("  Повне ім'я", default="Адміністратор")

        try:
            import httpx  # noqa: PLC0415

            resp = httpx.post(
                "http://localhost:8000/api/v1/auth/register",
                json={"email": email, "password": password, "full_name": full_name},
                timeout=5.0,
            )
            if resp.status_code == 200:
                console.print(f"[green]✓[/green] Адміністратор {email} створений")
            elif resp.status_code == 409:
                console.print(f"[yellow]~[/yellow] Користувач {email} вже існує")
            else:
                console.print(f"[red]✗[/red] Помилка: {resp.text}")
        except Exception:  # noqa: BLE001
            console.print("[yellow]⚠[/yellow]  Сервер не доступний.")
            console.print("   Спочатку запусти [cyan]grunt serve[/cyan], потім зареєструй адміна:")
            console.print(f"   [dim]POST http://localhost:8000/api/v1/auth/register[/dim]")

    # 6. Фінал
    console.print()
    console.print("[bold green]✅ Ґрунт ініціалізовано![/bold green]")
    console.print()
    console.print("Наступні кроки:")
    console.print("  [cyan]grunt serve[/cyan]          запустити сервер")
    console.print("  [cyan]grunt auth login[/cyan]     авторизуватись для CLI команд")
    console.print("  [cyan]grunt doctype list[/cyan]   переглянути DocTypes")
