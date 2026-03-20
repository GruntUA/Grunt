"""grunt auth * — авторизація для CLI команд."""

from __future__ import annotations

from pathlib import Path

import click
import httpx
from rich.console import Console

console = Console()


def _token_file() -> Path:
    return Path.home() / ".grunt_token"


def _get_token() -> str | None:
    tf = _token_file()
    return tf.read_text().strip() if tf.exists() else None


def _save_token(token: str) -> None:
    _token_file().write_text(token)


def _auth_headers() -> dict[str, str]:
    token = _get_token()
    if not token:
        console.print("[red]✗[/red] Не авторизовано. Запусти: [cyan]grunt auth login[/cyan]")
        raise SystemExit(1)
    return {"Authorization": f"Bearer {token}"}


@click.group()
def auth() -> None:
    """Авторизація для CLI команд."""


@auth.command("login")
@click.option("--api", default="http://localhost:8000", show_default=True)
def auth_login(api: str) -> None:
    """Авторизується і зберігає токен у ~/.grunt_token."""
    email = click.prompt("Email")
    password = click.prompt("Пароль", hide_input=True)

    try:
        resp = httpx.post(
            f"{api}/api/v1/auth/token",
            data={"username": email, "password": password},
            timeout=5.0,
        )
        if resp.status_code == 401:
            console.print("[red]✗[/red] Невірний email або пароль")
            return
        resp.raise_for_status()
        token = resp.json()["access_token"]
        _save_token(token)
        console.print(f"[green]✓[/green] Авторизовано як {email}")
        console.print("[dim]Токен збережено в ~/.grunt_token[/dim]")
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
        console.print(f"[red]✗[/red] Сервер {api} недоступний. Запусти [cyan]grunt serve[/cyan]")


@auth.command("logout")
def auth_logout() -> None:
    """Видаляє збережений токен."""
    tf = _token_file()
    if tf.exists():
        tf.unlink()
        console.print("[green]✓[/green] Вийшли з системи")
    else:
        console.print("[dim]Токен не знайдено[/dim]")


@auth.command("whoami")
@click.option("--api", default="http://localhost:8000", show_default=True)
def auth_whoami(api: str) -> None:
    """Показує поточного авторизованого користувача."""
    try:
        resp = httpx.get(
            f"{api}/api/v1/auth/me",
            headers=_auth_headers(),
            timeout=5.0,
        )
        resp.raise_for_status()
        body = resp.json()
        user = body.get("data", body)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
        console.print("[red]✗[/red] Сервер недоступний. Запусти [cyan]grunt serve[/cyan]")
        return

    console.print(f"[bold]{user['full_name']}[/bold]  [dim]{user['email']}[/dim]")
    if user.get("is_superadmin"):
        console.print("[cyan]Superadmin[/cyan]")
    roles = user.get("roles") or []
    if roles:
        console.print(f"Ролі: {', '.join(roles)}")
