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
    return Path(__file__).resolve().parent.parent.parent


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


def _run_package_update(upgrade: bool = False) -> None:
    """Синхронізує Python-оточення з ``uv.lock``.

    За замовчуванням застосовує САМЕ ті версії, що зафіксовані в lock-файлі
    (який щойно підтягнув ``git pull``) — це не ламає оточення. ``--all-extras``
    гарантує, що dev-інструменти й драйвери БД лишаються на місці.

    ``upgrade=True`` (прапорець ``--upgrade-packages``) додатково піднімає всі
    пакети до найновіших сумісних версій — робити свідомо.
    """
    app_dir = _grunt_app_dir()
    uv = _find_uv()
    if uv:
        cmd = [uv, "sync", "--all-extras"]
        if upgrade:
            cmd.append("--upgrade")
        console.print(f"  [dim]{' '.join(cmd[1:])}...[/dim]")
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env["PWD"] = str(app_dir)
        result = subprocess.run(cmd, cwd=str(app_dir), check=False, env=env)
        if result.returncode != 0:
            console.print("  [yellow]⚠[/yellow]  uv sync завершився з помилкою")
        else:
            _verify_toolchain(app_dir)
            console.print("  [green]✓[/green] Python пакети синхронізовані")
        return
    console.print("  [dim]uv не знайдено, використовую pip...[/dim]")
    result = subprocess.run(_pip_install_cmd(upgrade), cwd=str(app_dir), check=False)
    if result.returncode != 0:
        console.print("  [yellow]⚠[/yellow]  pip install завершився з помилкою")
    else:
        console.print("  [green]✓[/green] Python пакети синхронізовані")


# dev tooling — an installable list for the pip fallback (uv reads the
# [dependency-groups] table directly).
_DEV_DEPS = ["pytest", "pytest-asyncio", "pytest-cov", "httpx", "ruff", "mypy"]


def _pip_install_cmd(upgrade: bool) -> list[str]:
    cmd = [sys.executable, "-m", "pip", "install", "-e", ".", *_DEV_DEPS]
    if upgrade:
        cmd.insert(4, "--upgrade")
    return cmd


def _verify_toolchain(app_dir: Path) -> None:
    """Попереджає, якщо sync лишив оточення без dev-інструментів (напр. коли
    забули ``--all-extras``)."""
    venv = app_dir / ".venv" / "bin"
    py = venv / "python"
    if not py.exists():
        return
    has_pytest = (
        subprocess.run(
            [str(py), "-c", "import pytest"], capture_output=True, check=False
        ).returncode
        == 0
    )
    if not has_pytest or not (venv / "ruff").exists():
        console.print(
            "  [yellow]⚠[/yellow]  У .venv відсутні dev-пакети (pytest / ruff). "
            "Відновіть: [cyan]uv sync --all-extras[/cyan]"
        )


def _run_npm_install_for(app_dir: Path, upgrade: bool = False) -> None:
    mise = shutil.which("mise")
    npm_run = (
        [mise, "exec", "--", "npm"]
        if mise
        else ([shutil.which("npm")] if shutil.which("npm") else None)
    )
    if not npm_run:
        console.print("  [yellow]⚠[/yellow]  npm не знайдено")
        return
    if upgrade:
        console.print(f"  [dim]npm update ({app_dir.name})...[/dim]")
        result = subprocess.run([*npm_run, "update"], cwd=str(app_dir), check=False)
        if result.returncode == 0:
            subprocess.run([*npm_run, "audit", "fix"], cwd=str(app_dir), check=False)
            console.print("  [green]✓[/green] npm пакети оновлені")
        else:
            console.print("  [yellow]⚠[/yellow]  npm update завершився з помилкою")
        return
    # `npm ci` коли є lock — ставить РІВНО за package-lock.json, без правок.
    use_ci = (app_dir / "package-lock.json").exists()
    verb = "ci" if use_ci else "install"
    console.print(f"  [dim]npm {verb} ({app_dir.name})...[/dim]")
    result = subprocess.run([*npm_run, verb], cwd=str(app_dir), check=False)
    if result.returncode != 0 and use_ci:
        # lock розійшовся з package.json — відкат на install
        console.print("  [dim]npm ci не пройшов, пробую npm install...[/dim]")
        result = subprocess.run([*npm_run, "install"], cwd=str(app_dir), check=False)
    if result.returncode == 0:
        console.print("  [green]✓[/green] npm пакети встановлені")
    else:
        console.print("  [yellow]⚠[/yellow]  npm install завершився з помилкою")


def _run_migrations(site: str | None) -> None:
    try:
        from grunt.site.manager import site_manager

        if not (site or site_manager.get_sites()):
            console.print("  [dim]Жодного сайту — міграції пропущено[/dim]")
            return
    except Exception:
        pass  # site manager unavailable → let db_migrate decide

    from grunt.cli.db import db_migrate

    ctx = click.Context(db_migrate)
    try:
        ctx.invoke(db_migrate, dry_run=False, site=site)
    except SystemExit as exc:
        if exc.code:
            console.print("  [yellow]⚠[/yellow]  Міграції завершились з помилкою")
    except Exception as exc:  # noqa: BLE001 — update must not crash on migrate
        console.print(f"  [yellow]⚠[/yellow]  Міграції пропущено: {exc}")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@click.group("update")
def update_group() -> None:
    """Оновити фреймворк, додатки та залежності."""


@update_group.command("all")
@click.option("--cli", "update_cli", is_flag=True, default=False, help="Оновити тільки CLI")
@click.option(
    "--framework", "update_framework", is_flag=True, default=False, help="Оновити тільки фреймворк"
)
@click.option("--apps", "update_apps", is_flag=True, default=False, help="Оновити тільки додатки")
@click.option(
    "--skip-packages", is_flag=True, default=False, help="Не синхронізувати Python пакети"
)
@click.option("--skip-npm", is_flag=True, default=False, help="Не встановлювати npm пакети")
@click.option("--skip-migrate", is_flag=True, default=False, help="Не запускати міграції БД")
@click.option(
    "--upgrade-packages",
    is_flag=True,
    default=False,
    help="Підняти Python/npm пакети до нових версій (не лише синхронізувати з lock)",
)
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
    upgrade_packages: bool,
    no_deps: bool,
    site: str | None,
) -> None:
    """Оновити CLI, фреймворк, додатки, пакети та схему БД.

    \b
    Послідовність:
      1. git pull --rebase для CLI, фреймворку та додатків
      2. uv sync --all-extras (Python пакети — рівно за lock-файлом)
      3. npm install
      4. grunt migrate

    \b
    Без прапорців синхронізує все з підтягнутими lock-файлами (безпечно).
    --upgrade-packages — свідомо піднімає версії пакетів.
    З прапорцями компонентів — тільки вказані.

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
        _run_package_update(upgrade=upgrade_packages)
        console.print()
    else:
        console.print("[dim]Python пакети пропущено (--skip-packages)[/dim]")
        console.print()

    # ── 5. npm пакети ───────────────────────────────────────────────
    if not skip_npm:
        console.print("[bold cyan]npm пакети[/bold cyan]")
        grunt_dir = _grunt_app_dir()
        if grunt_dir.exists():
            _run_npm_install_for(grunt_dir, upgrade=upgrade_packages)
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


# ---------------------------------------------------------------------------
# grunt deps
# ---------------------------------------------------------------------------


@update_group.command("deps")
@click.option("-U", "--upgrade", is_flag=True, default=False, help="Оновити пакети до нових версій")
@click.option("--python-only", is_flag=True, default=False, help="Тільки Python (uv sync)")
@click.option("--npm-only", is_flag=True, default=False, help="Тільки npm install")
def deps(upgrade: bool, python_only: bool, npm_only: bool) -> None:
    """Встановити / оновити залежності (uv sync + npm install).

    \b
    Приклади:
      grunt deps              встановити всі залежності
      grunt deps -U           оновити до нових версій
      grunt deps --python-only
      grunt deps --npm-only
    """
    console.print("[bold]📦 Grunt Deps[/bold]")
    console.print()

    run_python = not npm_only
    run_npm = not python_only

    if run_python:
        console.print("[bold cyan]Python пакети[/bold cyan]")
        uv = _find_uv()
        app_dir = _grunt_app_dir()
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env["PWD"] = str(app_dir)
        if uv:
            cmd = [uv, "sync", "--all-extras"]
            if upgrade:
                cmd.append("--upgrade")
            label = "uv sync --all-extras" + (" --upgrade" if upgrade else "")
            console.print(f"  [dim]{label}...[/dim]")
            result = subprocess.run(cmd, cwd=str(app_dir), check=False, env=env)
            if result.returncode == 0:
                console.print("  [green]✓[/green] Python пакети встановлені")
            else:
                console.print("  [yellow]⚠[/yellow]  uv sync завершився з помилкою")
        else:
            console.print("  [dim]uv не знайдено, використовую pip...[/dim]")
            result = subprocess.run(_pip_install_cmd(upgrade), cwd=str(app_dir), check=False)
            if result.returncode == 0:
                console.print("  [green]✓[/green] Python пакети встановлені")
            else:
                console.print("  [yellow]⚠[/yellow]  pip install завершився з помилкою")
        console.print()

    if run_npm:
        console.print("[bold cyan]npm пакети[/bold cyan]")
        _run_npm_install_for(_grunt_app_dir(), upgrade=upgrade)
        console.print()

    console.print("[bold green]✅ Залежності встановлено[/bold green]")
