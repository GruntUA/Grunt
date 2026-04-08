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
def serve(port, reload):
    """Запуск сервера FastAPI."""
    click.echo(f"Запуск сервера на порту {port}...")
    cmd = ["uvicorn", "grunt.main:app", "--port", str(port)]
    if reload:
        cmd += [
            "--reload",
            "--reload-include",
            "*.js",
            "--reload-include",
            "*.json",
            "--reload-dir",
            str(Path(__file__).parents[3]),  # backend/
        ]
        grunt_apps = Path("grunt_apps")
        if grunt_apps.exists():
            cmd += ["--reload-dir", str(grunt_apps)]
    subprocess.run(cmd)


@click.command()
def worker():
    """Запуск воркера фонових завдань (TaskIQ)."""
    click.echo("Запуск воркера TaskIQ...")
    from grunt.core.tasks.registry import discover_tasks  # noqa: PLC0415

    apps_dir = Path("grunt_apps")
    discover_tasks(apps_dir)
    subprocess.run(["taskiq", "worker", "grunt.core.tasks.broker:broker"])
