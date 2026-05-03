"""grunt ui — керування shadcn-vue компонентами."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import click


# ── Helpers ───────────────────────────────────────────────────────────────────

def _app_dir() -> Path:
    """Root of the grunt app (where package.json and components.json live)."""
    # ui.py → cli/ → grunt/ → backend/ → apps/grunt/
    return Path(__file__).resolve().parent.parent.parent.parent


def _npm_runner() -> list[str]:
    """Return [mise, exec, --] or [npx] prefix for running npm binaries."""
    mise = shutil.which("mise")
    if mise:
        return [mise, "exec", "--", "npx"]
    npx = shutil.which("npx")
    if not npx:
        raise click.ClickException("npx не знайдено. Встановіть Node.js.")
    return [npx]


# Components that live in ui/ but are NOT in the shadcn-vue registry.
# They are custom framework components and should never be passed to the CLI.
_CUSTOM_COMPONENTS = frozenset({"spinner"})


def _installed_components(ui_dir: Path) -> list[str]:
    """Return shadcn-vue component names present in ui/ (excluding custom ones)."""
    if not ui_dir.exists():
        return []
    return sorted(
        d.name for d in ui_dir.iterdir()
        if d.is_dir()
        and (d / "index.ts").exists()
        and d.name not in _CUSTOM_COMPONENTS
    )


def _shadcn(app_dir: Path, args: list[str]) -> int:
    """Run npx shadcn-vue@latest <args> in app_dir, return exit code."""
    cmd = [*_npm_runner(), "shadcn-vue@latest", *args]
    click.echo(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=app_dir, check=False)
    return result.returncode


# ── Command group ─────────────────────────────────────────────────────────────

@click.group("ui")
def ui_group() -> None:
    """Керування shadcn-vue UI компонентами."""


@ui_group.command("add")
@click.argument("components", nargs=-1, required=True)
@click.option("--overwrite", is_flag=True, default=True, show_default=True,
              help="Перезаписати існуючі файли")
def ui_add(components: tuple[str, ...], overwrite: bool) -> None:
    """Додати один або кілька shadcn-vue компонентів.

    \b
    Приклади:
      grunt ui add empty
      grunt ui add dialog alert-dialog
    """
    app_dir = _app_dir()
    args = ["add", *components]
    if overwrite:
        args.append("--overwrite")
    code = _shadcn(app_dir, args)
    if code != 0:
        raise click.ClickException(f"shadcn-vue завершився з кодом {code}")
    click.echo(click.style("✔ Готово", fg="green"))


@ui_group.command("update")
@click.argument("components", nargs=-1, required=False)
@click.option("--skip-package", is_flag=True,
              help="Не оновлювати пакет shadcn-vue через npm")
def ui_update(components: tuple[str, ...], skip_package: bool) -> None:
    """Оновити shadcn-vue та його компоненти до останньої версії.

    Без аргументів оновлює всі встановлені компоненти.
    З аргументами — тільки вказані.

    \b
    Приклади:
      grunt ui update                   # оновити все
      grunt ui update button badge      # тільки button і badge
      grunt ui update --skip-package    # без оновлення npm-пакету
    """
    app_dir = _app_dir()
    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"

    # ── 1. Оновити npm-пакет shadcn-vue ──────────────────────────────────────
    if not skip_package:
        click.echo("── [1/2] Оновлення пакету shadcn-vue...")
        mise = shutil.which("mise")
        npm_runner = ([mise, "exec", "--", "npm"] if mise else
                      [shutil.which("npm") or "npm"])
        result = subprocess.run(
            [*npm_runner, "install", "shadcn-vue@latest"],
            cwd=app_dir, check=False,
        )
        if result.returncode != 0:
            click.echo(click.style("  [warn] npm install shadcn-vue@latest не вдалося", fg="yellow"), err=True)
    else:
        click.echo("── [1/2] Оновлення npm-пакету пропущено")

    # ── 2. Перевстановити компоненти ─────────────────────────────────────────
    targets = list(components) if components else _installed_components(ui_dir)

    if not targets:
        click.echo(click.style("  Компонентів не знайдено у frontend/src/components/ui/", fg="yellow"))
        return

    click.echo(f"\n── [2/2] Оновлення {len(targets)} компонент(ів): {', '.join(targets)}")
    code = _shadcn(app_dir, ["add", *targets, "--overwrite"])
    if code != 0:
        raise click.ClickException(f"shadcn-vue завершився з кодом {code}")

    click.echo(click.style("\n✔ Оновлення завершено", fg="green"))


@ui_group.command("list")
def ui_list() -> None:
    """Показати встановлені shadcn-vue компоненти."""
    app_dir = _app_dir()
    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"
    components = _installed_components(ui_dir)
    if not components:
        click.echo("Компонентів не знайдено.")
        return
    click.echo(f"Встановлено {len(components)} компонент(ів):\n")
    for name in components:
        click.echo(f"  • {name}")
