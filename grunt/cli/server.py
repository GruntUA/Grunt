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
    """Project initialization stub (does not create .env, the database or an admin yet)."""
    click.echo("Initializing Grunt...")
    click.echo("Done.")


@click.command()
@click.option("--port", default=8000, help="API port")
@click.option(
    "--reload",
    is_flag=True,
    default=True,
    help="Reload mode (on by default)",
)
@click.option("--no-frontend", is_flag=True, help="Do not start the frontend")
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
            click.echo("Skipping port 5173 cleanup: fuser is only supported on Linux.")
        click.echo("Starting the frontend (Vite) on port 5173...")
        frontend_process = subprocess.Popen(
            [*_npm_cmd(), "npm", "run", "dev"],
            cwd=root_dir,
            # Inherit terminal so Vite URL and errors are visible
            stdout=None,
            stderr=None,
        )

    click.echo(f"Starting the API server on port {port}...")
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
        # Watch inner Python packages of external apps so .py/.js/.json
        # changes trigger reload without picking up .git/, README, etc.
        apps_dir = root_dir / "apps"
        if apps_dir.exists():
            for app_dir in apps_dir.iterdir():
                if not app_dir.is_dir() or app_dir.name == "grunt":
                    continue
                # Inner package directory has the same name as the app
                inner = app_dir / app_dir.name
                watch_dir = inner if inner.is_dir() else app_dir
                cmd += ["--reload-dir", str(watch_dir)]

    try:
        subprocess.run(cmd, cwd=root_dir)
    except KeyboardInterrupt:
        click.echo("\nStopping servers...")
    finally:
        if frontend_process:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_process.kill()


@click.command()
def worker():
    """Start the background job worker (TaskIQ).

    Tasks are registered by grunt.tasks.worker, inside the worker process itself
    (TaskIQ starts it as a separate process, so imports here are not visible to it).
    """
    click.echo("Starting the TaskIQ worker...")
    subprocess.run(["taskiq", "worker", "grunt.tasks.worker:broker"])
