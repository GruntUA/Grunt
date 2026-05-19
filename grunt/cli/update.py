"""grunt update — оновлення CLI, фреймворку та додатків через git."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import click
from rich.console import Console

console = Console(force_terminal=True, color_system="truecolor")


# ---------------------------------------------------------------------------
# Bench / site discovery
# ---------------------------------------------------------------------------


def _get_bench_dir() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "apps").is_dir() and (parent / "sites").is_dir():
            return parent
    return None


def _get_site_dir() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "grunt.site").exists():
            return parent
    return None


def _find_apps_dir() -> Path | None:
    bench = _get_bench_dir()
    if bench:
        return bench / "apps"
    site = _get_site_dir()
    if site and (site / "apps").is_dir():
        return site / "apps"
    return None


def _grunt_app_dir() -> Path:
    """apps/grunt/ — корінь фреймворку (де pyproject.toml і package.json)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _find_uv() -> str | None:
    uv = shutil.which("uv")
    if uv:
        return uv
    for candidate in [
        Path.home() / ".local/bin/uv",
        Path.home() / ".cargo/bin/uv",
        Path.home() / ".local/share/mise/shims/uv",
    ]:
        if candidate.exists():
            return str(candidate)
    return None


def _run_mise(cwd: Path, *args: str) -> bool:
    mise = shutil.which("mise")
    if not mise:
        console.print("[red]✗[/red] mise не знайдено")
        return False
    subprocess.run([mise, "trust"], cwd=str(cwd), capture_output=True)
    cmd = [mise]
    # "install" — пряма команда mise, решта — задачі (mise run <task>)
    if args and args[0] in {"deps", "db:migrate", "serve", "dev", "bootstrap"}:
        cmd.append("run")
    cmd.extend(args)
    result = subprocess.run(cmd, cwd=str(cwd), env={**os.environ})
    return result.returncode == 0


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def _git_pull(path: Path, label: str) -> bool:
    if not (path / ".git").exists():
        console.print(f"  [yellow]⚠[/yellow]  {label}: не є git-репозиторієм, пропускаю")
        return False

    branch = (
        subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
        ).stdout.strip()
        or "?"
    )

    old_hash = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        capture_output=True,
        text=True,
    ).stdout.strip()

    console.print(f"  [dim]Оновлюю {label} ({branch})...[/dim]")

    result = subprocess.run(
        ["git", "pull", "--rebase", "--autostash"],
        cwd=str(path),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "could not read Username" in stderr or "Authentication failed" in stderr:
            console.print(f"  [yellow]⚠[/yellow]  {label}: немає доступу до GitHub")
            console.print("    [dim]Налаштуйте SSH-ключ або git credentials:[/dim]")
            console.print("    [dim]  ssh-keygen -t ed25519 && ssh-add ~/.ssh/id_ed25519[/dim]")
            console.print("    [dim]  git remote set-url origin git@github.com:ORG/REPO.git[/dim]")
        else:
            console.print(f"  [red]✗[/red] {label}: помилка git pull")
            if stderr:
                console.print(f"    [dim]{stderr}[/dim]")
        return False

    new_hash = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        capture_output=True,
        text=True,
    ).stdout.strip()

    if old_hash == new_hash:
        console.print(f"  [green]✓[/green] {label}: вже актуальний ({old_hash})")
    else:
        console.print(f"  [green]✓[/green] {label}: оновлено {old_hash} → {new_hash}")
        diff = subprocess.run(
            ["git", "diff", "--stat", f"{old_hash}..{new_hash}"],
            cwd=str(path),
            capture_output=True,
            text=True,
        )
        if diff.returncode == 0:
            for line in diff.stdout.strip().splitlines():
                line = line.strip()
                if "changed" in line and ("insertion" in line or "deletion" in line):
                    line = line.replace("(+)", "[green](+)[/green]").replace(
                        "(-)", "[red](-)[/red]"
                    )
                    console.print(f"    [cyan]{line}[/cyan]")
                else:
                    if "|" in line:
                        path_part, stats_part = line.rsplit("|", 1)
                        stats_part = re.sub(r"(\++)", r"[green]\1[/green]", stats_part)
                        stats_part = re.sub(r"(-+)", r"[red]\1[/red]", stats_part)
                        line = f"{path_part}|{stats_part}"
                    console.print(f"    [dim]{line}[/dim]")
    return True


def _install_deps(path: Path, label: str) -> None:
    """Встановлює рантайми та пакети через mise (лише якщо є mise.toml)."""
    mise_toml = path / "mise.toml"
    if not mise_toml.exists():
        return
    console.print(f"  [dim]Оновлюю рантайми для {label}...[/dim]")
    _run_mise(path, "install")
    with mise_toml.open("rb") as f:
        tasks = tomllib.load(f).get("tasks", {})
    if "deps" in tasks:
        console.print(f"  [dim]Встановлюю пакети для {label} (mise run deps)...[/dim]")
        _run_mise(path, "deps")


# ---------------------------------------------------------------------------
# package / npm / migrate helpers
# ---------------------------------------------------------------------------


def _run_package_update() -> None:
    app_dir = _grunt_app_dir()
    uv = _find_uv()
    if uv:
        console.print("  [dim]uv sync --upgrade...[/dim]")
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env["PWD"] = str(app_dir)
        result = subprocess.run(
            [uv, "sync", "--upgrade", "--all-extras"], cwd=str(app_dir), check=False, env=env
        )
        if result.returncode != 0:
            console.print("  [yellow]⚠[/yellow]  uv sync --upgrade завершився з помилкою")
        else:
            console.print("  [green]✓[/green] Python пакети оновлені")
        return
    console.print("  [dim]uv не знайдено, використовую pip...[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "grunt"],
        cwd=str(app_dir),
        check=False,
    )
    if result.returncode != 0:
        console.print("  [yellow]⚠[/yellow]  pip install --upgrade завершився з помилкою")
    else:
        console.print("  [green]✓[/green] Python пакети оновлені")


def _run_npm_install_for(app_dir: Path) -> None:
    mise = shutil.which("mise")
    npm_run = (
        [mise, "exec", "--", "npm"]
        if mise
        else ([shutil.which("npm")] if shutil.which("npm") else None)
    )
    if not npm_run:
        console.print("  [yellow]⚠[/yellow]  npm не знайдено")
        return
    console.print(f"  [dim]npm install ({app_dir.name})...[/dim]")
    result = subprocess.run([*npm_run, "install"], cwd=str(app_dir), check=False)
    if result.returncode != 0:
        nm = app_dir / "node_modules"
        if nm.exists():
            console.print("  [dim]Очищення node_modules, повторна спроба...[/dim]")
            shutil.rmtree(nm)
        result = subprocess.run([*npm_run, "install"], cwd=str(app_dir), check=False)
    if result.returncode == 0:
        subprocess.run([*npm_run, "audit", "fix"], cwd=str(app_dir), check=False)
        console.print("  [green]✓[/green] npm пакети встановлені")
    else:
        console.print("  [yellow]⚠[/yellow]  npm install завершився з помилкою")


def _run_migrations(site: str | None) -> None:
    from grunt.cli.db import db_migrate  # noqa: PLC0415

    ctx = click.Context(db_migrate)
    ctx.invoke(db_migrate, dry_run=False, site=site)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@click.command("update")
@click.option("--cli", "update_cli", is_flag=True, default=False, help="Оновити тільки CLI")
@click.option(
    "--framework", "update_framework", is_flag=True, default=False, help="Оновити тільки фреймворк"
)
@click.option("--apps", "update_apps", is_flag=True, default=False, help="Оновити тільки додатки")
@click.option("--skip-packages", is_flag=True, default=False, help="Не оновлювати Python пакети")
@click.option("--skip-npm", is_flag=True, default=False, help="Не встановлювати npm пакети")
@click.option("--skip-migrate", is_flag=True, default=False, help="Не запускати міграції БД")
@click.option(
    "--no-deps", is_flag=True, default=False, help="Не встановлювати залежності після git pull"
)
@click.option("--site", default=None, help="Назва сайту (для migrate)")
def update(
    update_cli: bool,
    update_framework: bool,
    update_apps: bool,
    skip_packages: bool,
    skip_npm: bool,
    skip_migrate: bool,
    no_deps: bool,
    site: str | None,
) -> None:
    """Оновити CLI, фреймворк, додатки, пакети та схему БД.

    \b
    Послідовність:
      1. git pull --rebase для CLI, фреймворку та додатків
      2. uv sync --upgrade (Python пакети)
      3. npm install
      4. grunt migrate

    \b
    Без прапорців оновлює все.
    З прапорцями — тільки вказані компоненти.

    \b
    Приклади:
      grunt update                  оновити все
      grunt update --apps           тільки додатки
      grunt update --skip-migrate   без міграцій БД
      grunt update --no-deps        без mise install після git pull
    """
    update_all = not (update_cli or update_framework or update_apps)

    console.print("[bold]⚡ Grunt Update[/bold]")
    console.print()

    # ── 1. CLI ──────────────────────────────────────────────────────
    if update_all or update_cli:
        console.print("[bold cyan]CLI[/bold cyan]")
        cli_dir = Path.home() / ".grunt-cli"
        if (cli_dir / ".git").exists():
            _git_pull(cli_dir, "grunt-cli")
            if not no_deps:
                _install_deps(cli_dir, "grunt-cli")
        else:
            console.print("  [yellow]⚠[/yellow]  ~/.grunt-cli не є git-репозиторієм, пропускаю")
        console.print()

    # ── 2. Framework ────────────────────────────────────────────────
    if update_all or update_framework:
        console.print("[bold cyan]Фреймворк[/bold cyan]")
        framework_dir = _grunt_app_dir()
        if framework_dir.exists():
            _git_pull(framework_dir, "grunt")
            if not no_deps:
                _install_deps(framework_dir, "grunt")
        else:
            console.print("  [yellow]⚠[/yellow]  Grunt framework не знайдено")
        console.print()

    # ── 3. Apps ─────────────────────────────────────────────────────
    if update_all or update_apps:
        console.print("[bold cyan]Додатки[/bold cyan]")
        apps_dir = _find_apps_dir()
        if apps_dir and apps_dir.exists():
            app_dirs = sorted(
                p
                for p in apps_dir.iterdir()
                if p.is_dir() and p.name != "grunt" and (p / ".git").exists()
            )
            if app_dirs:
                for app_dir in app_dirs:
                    _git_pull(app_dir, app_dir.name)
                    if not no_deps:
                        _install_deps(app_dir, app_dir.name)
            else:
                console.print("  [dim]Немає додатків з git-репозиторієм[/dim]")
        else:
            console.print("  [dim]Директорію додатків не знайдено[/dim]")
        console.print()

    # ── 4. Python пакети ────────────────────────────────────────────
    if not skip_packages:
        console.print("[bold cyan]Python пакети[/bold cyan]")
        _run_package_update()
        console.print()
    else:
        console.print("[dim]Python пакети пропущено (--skip-packages)[/dim]")
        console.print()

    # ── 5. npm пакети ───────────────────────────────────────────────
    if not skip_npm:
        console.print("[bold cyan]npm пакети[/bold cyan]")
        grunt_dir = _grunt_app_dir()
        if grunt_dir.exists():
            _run_npm_install_for(grunt_dir)
        else:
            console.print("  [dim]Grunt app директорія не знайдена[/dim]")
        console.print()
    else:
        console.print("[dim]npm пропущено (--skip-npm)[/dim]")
        console.print()

    # ── 6. Міграція БД ──────────────────────────────────────────────
    if not skip_migrate:
        console.print("[bold cyan]Міграція БД[/bold cyan]")
        _run_migrations(site)
        console.print()
    else:
        console.print("[dim]Міграція БД пропущена (--skip-migrate)[/dim]")
        console.print()

    console.print("[bold green]✅ Оновлення завершено[/bold green]")
