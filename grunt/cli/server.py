import shutil
import subprocess
import sys
from pathlib import Path

import click


def _npm_cmd() -> list[str]:
    """Return an npm invocation that uses the mise-managed Node when available."""
    mise = shutil.which("mise")
    if mise:
        return [mise, "exec", "--"]
    return []


@click.command()
def init():
    """Заглушка ініціалізації проєкту (поки без створення .env, БД та адміна)."""
    click.echo("Ініціалізація Ґрунт...")
    click.echo("Готово.")


@click.command()
@click.option("--port", default=8000, help="Порт для API")
@click.option("--reload", is_flag=True, default=True, help="Режим перезавантаження (увімкнено за замовчуванням)")
@click.option("--no-frontend", is_flag=True, help="Не запускати фронтенд")
def serve(port, reload, no_frontend):
    root_dir = Path(__file__).parents[2]

    frontend_process = None
    if not no_frontend:
        # Kill any stale process on port 5173 so Vite always starts on the expected port
        if sys.platform.startswith("linux"):
            subprocess.run(
                ["fuser", "-k", "5173/tcp"],
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            click.echo("Пропуск очищення порту 5173: команда fuser підтримується лише на Linux.")
        click.echo("Запуск фронтенда (Vite) на порту 5173...")
        frontend_process = subprocess.Popen(
            [*_npm_cmd(), "npm", "run", "dev"],
            cwd=root_dir,
            # Inherit terminal so Vite URL and errors are visible
            stdout=None,
            stderr=None,
        )

    click.echo(f"Запуск API сервера на порту {port}...")
    cmd = ["uvicorn", "grunt.main:app", "--port", str(port)]
    if reload:
        cmd += [
            "--reload",
            "--reload-include",
            "*.py",
            "--reload-include",
            "*.js",
            "--reload-include",
            "*.json",
            "--reload-dir",
            str(root_dir / "grunt"),
        ]
        # Also watch external apps so changes to doctypes, hooks, etc. trigger reload
        apps_dir = root_dir / "apps"
        if apps_dir.exists():
            for app_dir in apps_dir.iterdir():
                if app_dir.is_dir() and app_dir.name != "grunt":
                    cmd += ["--reload-dir", str(app_dir)]

    try:
        subprocess.run(cmd, cwd=root_dir)
    except KeyboardInterrupt:
        click.echo("\nЗупинка серверів...")
    finally:
        if frontend_process:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_process.kill()


@click.command()
def worker():
    """Запуск воркера фонових завдань (TaskIQ)."""
    from grunt.site.manager import site_manager  # noqa: PLC0415
    from grunt.tasks.registry import discover_tasks  # noqa: PLC0415

    click.echo("Запуск воркера TaskIQ...")
    discover_tasks(site_manager.bench_dir / "apps")
    subprocess.run(["taskiq", "worker", "grunt.tasks.broker:broker"])
