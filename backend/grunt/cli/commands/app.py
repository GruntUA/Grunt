"""grunt app * — управління додатками."""

from __future__ import annotations

import json
from pathlib import Path

import click
import httpx
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()

_GRUNT_APPS_DIR = Path.home() / "grunt-apps"


def _token_file() -> Path:
    return Path.home() / ".grunt_token"


def _get_token() -> str | None:
    tf = _token_file()
    return tf.read_text().strip() if tf.exists() else None


def _auth_headers() -> dict[str, str]:
    token = _get_token()
    if not token:
        console.print("[red]✗[/red] Не авторизовано. Запусти: [cyan]grunt auth login[/cyan]")
        raise SystemExit(1)
    return {"Authorization": f"Bearer {token}"}


@click.group()
def app() -> None:
    """Команди для управління Grunt-додатками."""


@app.command("create")
@click.argument("name")
@click.option("--title", default=None, help="Назва додатку")
@click.option("--output-dir", "-o", default=".", show_default=True, help="Директорія для створення")
def app_create(name: str, title: str | None, output_dir: str) -> None:
    """Створити структуру нового Grunt-додатку."""
    app_dir = Path(output_dir) / name
    if app_dir.exists():
        console.print(f"[red]✗[/red] Директорія '{app_dir}' вже існує")
        raise SystemExit(1)

    title = title or name.replace("_", " ").title()

    # Create directory structure
    (app_dir / "doctypes").mkdir(parents=True)
    (app_dir / "fixtures").mkdir(parents=True)

    # app.json
    app_json = {
        "name": name,
        "title": title,
        "version": "0.1.0",
        "modules": [],
    }
    (app_dir / "app.json").write_text(json.dumps(app_json, ensure_ascii=False, indent=2))

    # README stub
    (app_dir / "README.md").write_text(f"# {title}\n\nGrunt app: {name}\n")

    console.print(f"[green]✓[/green] Додаток [bold]{name}[/bold] створено у {app_dir}")
    console.print(f"  [dim]{app_dir}/app.json[/dim]")
    console.print(f"  [dim]{app_dir}/doctypes/[/dim]")


@app.command("install")
@click.argument("name")
@click.option("--api", default="http://localhost:8000", show_default=True)
@click.option("--apps-dir", default=str(_GRUNT_APPS_DIR), show_default=True)
def app_install(name: str, api: str, apps_dir: str) -> None:
    """Встановити додаток з директорії grunt-apps."""
    app_path = Path(apps_dir) / name / "app.json"
    if not app_path.exists():
        console.print(f"[red]✗[/red] Файл app.json не знайдено: {app_path}")
        raise SystemExit(1)

    app_data = json.loads(app_path.read_text())

    try:
        resp = httpx.post(
            f"{api}/api/v1/apps/",
            headers=_auth_headers(),
            json=app_data,
            timeout=10.0,
        )
        if resp.status_code == 409:
            console.print(f"[yellow]![/yellow] Додаток '{name}' вже встановлено")
            return
        resp.raise_for_status()
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] Не можу підключитись до {api}")
        raise SystemExit(1)

    console.print(f"[green]✓[/green] Додаток [bold]{name}[/bold] встановлено")


@app.command("list")
@click.option("--api", default="http://localhost:8000", show_default=True)
def app_list(api: str) -> None:
    """Показати список встановлених додатків."""
    try:
        resp = httpx.get(
            f"{api}/api/v1/apps/",
            headers=_auth_headers(),
            timeout=5.0,
        )
        resp.raise_for_status()
        apps = resp.json().get("data", [])
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] Не можу підключитись до {api}")
        raise SystemExit(1)

    if not apps:
        console.print("[dim]Додатків не встановлено[/dim]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    table.add_column("Назва", style="cyan")
    table.add_column("Заголовок")
    table.add_column("Версія", style="dim")
    table.add_column("Встановлено", style="dim")

    for a in apps:
        table.add_row(
            a["name"],
            a["title"],
            a["version"],
            (a.get("installed_at") or "")[:10],
        )

    console.print(table)


@app.command("export")
@click.argument("name")
@click.option("--api", default="http://localhost:8000", show_default=True)
@click.option("--output-dir", "-o", default=".", show_default=True)
def app_export(name: str, api: str, output_dir: str) -> None:
    """Експортувати DocTypes додатку у JSON-файли."""
    try:
        resp = httpx.get(
            f"{api}/api/v1/meta/doctypes",
            headers=_auth_headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        doctypes = resp.json().get("data", [])
    except httpx.ConnectError:
        console.print(f"[red]✗[/red] Не можу підключитись до {api}")
        raise SystemExit(1)

    out_dir = Path(output_dir) / name / "doctypes"
    out_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    for dt in doctypes:
        dt_file = out_dir / f"{dt['name']}.json"
        dt_file.write_text(json.dumps(dt, ensure_ascii=False, indent=2))
        exported += 1

    console.print(f"[green]✓[/green] Експортовано {exported} DocType(s) у {out_dir}")
