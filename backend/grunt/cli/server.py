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
    root_dir = Path(__file__).parents[3]
    
    frontend_process = None
    if not no_frontend:
        # Kill any stale process on port 5173 so Vite always starts on the expected port
        subprocess.run(
            ["fuser", "-k", "5173/tcp"],
            stderr=subprocess.DEVNULL,
            check=False,
        )
        click.echo("Запуск фронтенда (Vite) на порту 5173...")
        frontend_process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=root_dir,
            # Inherit terminal so Vite URL and errors are visible
            stdout=None,
            stderr=None,
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
    from grunt.core.site.manager import site_manager  # noqa: PLC0415
    from grunt.core.tasks.registry import discover_tasks  # noqa: PLC0415

    click.echo("Запуск воркера TaskIQ...")
    discover_tasks(site_manager.bench_dir / "apps")
    subprocess.run(["taskiq", "worker", "grunt.core.tasks.broker:broker"])
