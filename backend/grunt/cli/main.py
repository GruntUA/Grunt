
import click
import subprocess
import os
import sys
from pathlib import Path

@click.group()
def cli():
    """Ґрунт CLI — інструмент управління фреймворком."""
    pass

@cli.command()
def init():
    """Ініціалізація проєкту (створення .env, БД та адміна)."""
    click.echo("Ініціалізація Ґрунт...")
    # Add implementation later based on PHASES.md
    click.echo("Готово.")

@cli.command()
@click.option("--port", default=8000, help="Порт для API")
@click.option("--reload", is_flag=True, help="Режим перезавантаження")
def serve(port, reload):
    """Запуск сервера FastAPI."""
    click.echo(f"Запуск сервера на порту {port}...")
    cmd = ["uvicorn", "grunt.main:app", "--port", str(port)]
    if reload:
        cmd.append("--reload")
    subprocess.run(cmd)

@cli.command()
def worker():
    """Запуск воркера фонових завдань (TaskIQ)."""
    click.echo("Запуск воркера TaskIQ...")
    # Discover tasks before running
    from grunt.main import lifespan
    from grunt.core.tasks.registry import discover_tasks
    
    apps_dir = Path("grunt_apps")
    discover_tasks(apps_dir)
    
    # Run taskiq worker
    # We use subprocess to run the taskiq CLI or use its programmatic API
    cmd = ["taskiq", "worker", "grunt.core.tasks.broker:broker"]
    subprocess.run(cmd)

if __name__ == "__main__":
    cli()
