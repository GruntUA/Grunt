"""grunt update — оновити фреймворк та всі додатки."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import shutil
import subprocess
import sys

import click
from rich.console import Console

console = Console(force_terminal=True, color_system="truecolor")


@click.command("update")
@click.option("--skip-migrate", is_flag=True, help="Не запускати grunt migrate після оновлення")
@click.option("--skip-packages", is_flag=True, help="Не оновлювати Python пакети")
@click.option("--skip-npm", is_flag=True, help="Не встановлювати npm пакети")
@click.option("--skip-git", is_flag=True, help="Не оновлювати додатки з git")
@click.option("--site", default=None, help="Назва сайту (для migrate)")
def update(skip_migrate: bool, skip_packages: bool, skip_npm: bool, skip_git: bool, site: str | None) -> None:
    """Оновити фреймворк: додатки + пакети + міграція схеми БД.

    Послідовність:

    \b
    1. git pull --rebase для всіх додатків
    2. uv sync --upgrade
    3. npm install
    4. grunt migrate

    Використовуй після оновлення версії Grunt або встановлення нових додатків.
    """
    # ── 0. Оновити додатки з git ────────────────────────────────────────────────
    if not skip_git:
        console.print("── [0/4] Оновлення додатків з git...")
        _pull_apps_from_git()
    else:
        console.print("── [0/4] Оновлення додатків з git пропущено (--skip-git)")

    # ── 1. Оновити Python пакети ──────────────────────────────────────────────
    if not skip_packages:
        console.print("\n── [1/4] Оновлення Python пакетів...")
        _run_package_update()
    else:
        console.print("── [1/4] Оновлення Python пакетів пропущено (--skip-packages)")

    # ── 2. Встановити npm пакети ──────────────────────────────────────────────
    if not skip_npm:
        console.print("\n── [2/4] Встановлення npm пакетів...")
        _run_npm_install()
    else:
        console.print("── [2/4] npm install пропущено (--skip-npm)")

    # ── 3. Міграція схеми БД ──────────────────────────────────────────────────
    if not skip_migrate:
        console.print("\n── [3/4] Міграція схеми БД (grunt migrate)...")
        from grunt.cli.db import db_migrate  # noqa: PLC0415

        ctx = click.Context(db_migrate)
        ctx.invoke(db_migrate, dry_run=False, site=site)
    else:
        console.print("── [3/4] Міграція пропущена (--skip-migrate)")

    console.print("\nОновлення завершено.")


def _grunt_app_dir() -> Path:
    """Return the grunt app root (where pyproject.toml and package.json live)."""
    from pathlib import Path  # noqa: PLC0415

    # update.py lives at apps/grunt/backend/grunt/cli/update.py
    # → 4 levels up = apps/grunt/
    return Path(__file__).resolve().parent.parent.parent.parent


def _get_apps_parent_dir() -> Path:
    """Return the apps/ directory that contains all apps (grunt, hrm, etc)."""
    from pathlib import Path  # noqa: PLC0415

    # update.py lives at apps/grunt/backend/grunt/cli/update.py
    # → 5 levels up = apps/
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _pull_apps_from_git() -> None:
    """Pull updates from git for all apps that have a .git directory.
    
    Skips apps without git repositories (they're not version-controlled).
    """
    from pathlib import Path  # noqa: PLC0415

    apps_dir = _get_apps_parent_dir()
    
    if not apps_dir.exists():
        console.print(f"  [yellow]⚠[/yellow]  Директорія {apps_dir} не знайдена")
        return
    
    # Find all directories with .git (excluding non-app directories)
    app_dirs = [
        d for d in apps_dir.iterdir()
        if d.is_dir() and (d / ".git").exists() and not d.name.startswith(".")
    ]
    
    if not app_dirs:
        console.print("  [dim]Немає додатків з git для оновлення[/dim]")
        return
    
    for app_dir in sorted(app_dirs):
        app_name = app_dir.name
        
        # Get current branch
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(app_dir),
            capture_output=True,
            text=True,
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        
        # Get old commit hash
        old_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(app_dir),
            capture_output=True,
            text=True,
        ).stdout.strip()
        
        # Pull with rebase
        result = subprocess.run(
            ["git", "pull", "--rebase", "--autostash"],
            cwd=str(app_dir),
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "could not read Username" in stderr or "Authentication failed" in stderr:
                console.print(f"  [yellow]⚠[/yellow]  {app_name}: немає доступу до GitHub")
                console.print("    [dim]Налаштуйте SSH-ключ або git credentials:[/dim]")
                console.print("    [dim]ssh-keygen -t ed25519 && ssh-add ~/.ssh/id_ed25519[/dim]")
            else:
                console.print(f"  [red]✗[/red] {app_name}: помилка git pull")
                if stderr:
                    console.print(f"    [dim]{stderr}[/dim]")
        else:
            # Get new commit hash
            new_hash = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(app_dir),
                capture_output=True,
                text=True,
            ).stdout.strip()
            
            if old_hash == new_hash:
                console.print(f"  [green]✓[/green] {app_name} ({branch}): вже актуальний ({old_hash})")
            else:
                console.print(f"  [green]✓[/green] {app_name} ({branch}): оновлено {old_hash} → {new_hash}")



def _run_npm_install() -> None:
    """Run npm install in the grunt app root (where package.json lives).

    Uses mise-managed Node when available (respects the version in mise.toml),
    otherwise falls back to the system npm.
    On ENOTEMPTY failures (corrupted node_modules) cleans and retries once.
    """
    import shutil as _shutil  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    app_dir = _grunt_app_dir()

    mise = shutil.which("mise")
    if mise:
        npm_run = [mise, "exec", "--", "npm"]
    else:
        npm = shutil.which("npm")
        if not npm:
            console.print("  [yellow]⚠[/yellow]  npm не знайдено, пропускаю встановлення npm пакетів")
            return
        npm_run = [npm]

    cmd = [*npm_run, "install"]
    result = subprocess.run(cmd, cwd=app_dir, check=False)

    if result.returncode != 0:
        # Retry once after cleaning node_modules (fixes ENOTEMPTY and stale lock issues)
        nm = Path(app_dir) / "node_modules"
        if nm.exists():
            console.print("  [dim]Очищення node_modules, повторна спроба...[/dim]")
            _shutil.rmtree(nm)
        result = subprocess.run(cmd, cwd=app_dir, check=False)

    if result.returncode != 0:
        console.print("  [yellow]⚠[/yellow]  npm install завершився з помилкою")
        return

    subprocess.run([*npm_run, "audit", "fix"], cwd=app_dir, check=False)


def _run_package_update() -> None:
    """Run the best available package manager to upgrade dependencies."""
    app_dir = _grunt_app_dir()

    # uv (preferred)
    if shutil.which("uv"):
        import os  # noqa: PLC0415

        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        result = subprocess.run(["uv", "sync", "--upgrade"], cwd=app_dir, check=False, env=env)
        if result.returncode != 0:
            console.print("  [yellow]⚠[/yellow]  uv sync --upgrade завершився з помилкою")
        return

    # pip fallback
    console.print("  [dim]uv не знайдено, використовую pip...[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "grunt"],
        cwd=app_dir,
        check=False,
    )
    if result.returncode != 0:
        console.print("  [yellow]⚠[/yellow]  pip install --upgrade завершився з помилкою")
