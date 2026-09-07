"""grunt ui — керування shadcn-vue компонентами."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

# ── Helpers ───────────────────────────────────────────────────────────────────


def _app_dir() -> Path:
    """Root of the grunt app (where package.json and components.json live)."""
    # ui.py → cli/ → grunt/ → apps/grunt/
    return Path(__file__).resolve().parent.parent.parent


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
# They are custom framework components and should never be passed to the CLI
# (the registry returns 404 for these names).
_CUSTOM_COMPONENTS = frozenset(
    {
        "spinner",
        "date-picker",
        "multi-select",
        "native-select",
        "tree-select",
    }
)


def _installed_components(ui_dir: Path) -> list[str]:
    """Return shadcn-vue component names present in ui/ (excluding custom ones)."""
    if not ui_dir.exists():
        return []
    return sorted(
        d.name
        for d in ui_dir.iterdir()
        if d.is_dir() and (d / "index.ts").exists() and d.name not in _CUSTOM_COMPONENTS
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
@click.option(
    "--overwrite", is_flag=True, default=True, show_default=True, help="Перезаписати існуючі файли"
)
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
def ui_update(components: tuple[str, ...]) -> None:
    """Перевстановити shadcn-vue компоненти з останнього реєстру (--overwrite).

    Без аргументів оновлює всі встановлені компоненти.
    З аргументами — тільки вказані.

    `npx shadcn-vue@latest` завжди тягне останню версію CLI/реєстру, тож
    окремо ставити npm-пакет не треба.

    \b
    Приклади:
      grunt ui update                   # оновити все
      grunt ui update button badge      # тільки button і badge
    """
    app_dir = _app_dir()
    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"

    targets = list(components) if components else _installed_components(ui_dir)

    if not targets:
        click.echo(
            click.style(f"  Компонентів не знайдено у {ui_dir}", fg="yellow")
        )
        return

    click.echo(f"── Оновлення {len(targets)} компонент(ів): {', '.join(targets)}")
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
