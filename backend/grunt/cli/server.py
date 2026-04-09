import subprocess
from pathlib import Path

import click


@click.command()
def init():
    """Ініціалізація проєкту (створення .env, БД та адміна)."""
    click.echo("Ініціалізація Ґрунт...")
    click.echo("Готово.")


@click.command()
@click.option("--port", default=8000, help="Порт для API")
@click.option("--reload", is_flag=True, help="Режим перезавантаження")
@click.option("--no-frontend", is_flag=True, help="Не запускати фронтенд")
def serve(port, reload, no_frontend):
    """Запуск сервера FastAPI (та Vite за замовчуванням)."""
    root_dir = Path(__file__).parents[3]
    
    frontend_process = None
    if not no_frontend:
        click.echo("Запуск фронтенда (Vite)...")
        # Ensure we run from the project root where package.json is
        frontend_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=root_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    click.echo(f"Запуск API сервера на порту {port}...")
    cmd = ["uvicorn", "backend.grunt.main:app", "--port", str(port)]
    if reload:
        cmd += [
            "--reload",
            "--reload-include", "*.js",
            "--reload-include", "*.json",
            "--reload-dir", str(root_dir / "backend"),
        ]
        grunt_apps = root_dir / "grunt_apps"
        if grunt_apps.exists():
            cmd += ["--reload-dir", str(grunt_apps)]
    
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
    click.echo("Запуск воркера TaskIQ...")
    from grunt.core.tasks.registry import discover_tasks  # noqa: PLC0415

    apps_dir = Path("grunt_apps")
    discover_tasks(apps_dir)
    subprocess.run(["taskiq", "worker", "grunt.core.tasks.broker:broker"])
