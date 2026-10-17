"""grunt ui - керування shadcn-vue компонентами."""

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click

# Helpers


def _app_dir() -> Path:
    """Root of the grunt app (where package.json and components.json live)."""
    # ui.py -> cli/ -> grunt/ -> apps/grunt/
    return Path(__file__).resolve().parent.parent.parent


def _node_runner(binary: str) -> list[str]:
    """Return [mise, exec, --, binary] or [binary] for running a Node.js tool."""
    mise = shutil.which("mise")
    if mise:
        return [mise, "exec", "--", binary]
    found = shutil.which(binary)
    if not found:
        raise click.ClickException(f"{binary} not found. Install Node.js.")
    return [found]


# Components that live in ui/ but are NOT in the shadcn-vue registry
# (the registry returns 404 for these names) - custom framework compositions
# that must never be passed to the CLI.
_CUSTOM_COMPONENTS = frozenset(
    {
        "date-picker",
        "multi-select",
        "tree-select",
    }
)

# The legacy style: under Tailwind v4 the CLI resolves it to new-york-v4.
_LEGACY_STYLE = "new-york"

# Lists every `<base>-<style>` the installed CLI knows (schema.json and the
# registry's own styles/index.json both lag behind it).
_PRESET_STYLES_JS = (
    "import('shadcn-vue/preset').then(m => console.log(JSON.stringify("
    "m.PRESET_BASES.flatMap(b => m.PRESET_STYLES.map(s => `${b}-${s}`)))))"
)
_REGISTRY_STYLE_URL = "https://shadcn-vue.com/r/styles/{style}/index.json"

# Defines the data-open:/data-checked:/… variants the reka-* components use.
_SHADCN_CSS_IMPORT = '@import "shadcn-vue/tailwind.css";'


def _installed_components(ui_dir: Path) -> list[str]:
    """Return shadcn-vue component names present in ui/ (excluding custom ones)."""
    if not ui_dir.exists():
        return []
    return sorted(
        d.name
        for d in ui_dir.iterdir()
        if d.is_dir() and (d / "index.ts").exists() and d.name not in _CUSTOM_COMPONENTS
    )


def _in_registry(style: str) -> bool:
    # The registry answers 403 to urllib's default User-Agent.
    request = urllib.request.Request(
        _REGISTRY_STYLE_URL.format(style=style), headers={"User-Agent": "grunt-cli"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise click.ClickException(f"shadcn-vue registry answered {e.code} for {style}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise click.ClickException(f"shadcn-vue registry is unreachable: {e}") from e


def _available_styles(app_dir: Path) -> list[str]:
    """Styles of the installed shadcn-vue CLI that the registry actually serves."""
    result = subprocess.run(
        [*_node_runner("node"), "-e", _PRESET_STYLES_JS],
        cwd=app_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise click.ClickException(f"Could not read shadcn-vue presets: {result.stderr.strip()}")
    candidates = [_LEGACY_STYLE, *json.loads(result.stdout)]
    with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        served = list(pool.map(_in_registry, candidates))
    return [style for style, ok in zip(candidates, served, strict=True) if ok]


def _shadcn(app_dir: Path, args: list[str]) -> int:
    """Run the project's shadcn-vue CLI with <args> in app_dir, return exit code."""
    cmd = [*_node_runner("npx"), "shadcn-vue", *args]
    click.echo(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=app_dir, check=False)
    return result.returncode


# Command group


@click.group("ui")
def ui_group() -> None:
    """Manage shadcn-vue UI components."""


@ui_group.command("add")
@click.argument("components", nargs=-1, required=True)
@click.option(
    "--overwrite", is_flag=True, default=True, show_default=True, help="Overwrite existing files"
)
def ui_add(components: tuple[str, ...], overwrite: bool) -> None:
    """Add one or more shadcn-vue components.

    \b
    Examples:
      grunt ui add empty
      grunt ui add dialog alert-dialog
    """
    app_dir = _app_dir()
    args = ["add", *components]
    if overwrite:
        args.append("--overwrite")
    code = _shadcn(app_dir, args)
    if code != 0:
        raise click.ClickException(f"shadcn-vue exited with code {code}")
    click.echo(click.style("✔ Done", fg="green"))


@ui_group.command("update")
@click.argument("components", nargs=-1, required=False)
def ui_update(components: tuple[str, ...]) -> None:
    """Reinstall shadcn-vue components from the registry (--overwrite).

    Without arguments, updates every installed component.
    With arguments, only the given ones.

    Uses the project's shadcn-vue devDependency, the same version whose
    tailwind.css main.css imports; `npm update shadcn-vue` moves both.

    \b
    Examples:
      grunt ui update                   # update everything
      grunt ui update button badge      # only button and badge
    """
    app_dir = _app_dir()
    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"

    targets = list(components) if components else _installed_components(ui_dir)

    if not targets:
        click.echo(click.style(f"  No components found in {ui_dir}", fg="yellow"))
        return

    click.echo(f"── Updating {len(targets)} component(s): {', '.join(targets)}")
    code = _shadcn(app_dir, ["add", *targets, "--overwrite"])
    if code != 0:
        raise click.ClickException(f"shadcn-vue exited with code {code}")

    click.echo(click.style("\n✔ Update complete", fg="green"))


@ui_group.command("style")
@click.argument("style", required=False)
def ui_style(style: str | None) -> None:
    """Show or switch the shadcn-vue style of every component in ui/.

    Writes `style` to components.json and reinstalls the installed components
    from that style's registry.

    The choices are the styles of the installed shadcn-vue CLI that the
    registry serves; `npm update shadcn-vue` brings new ones.

    \b
    Examples:
      grunt ui style                # current style and the choices
      grunt ui style reka-nova      # switch
    """
    app_dir = _app_dir()
    config_path = app_dir / "components.json"
    config = json.loads(config_path.read_text())
    current = config.get("style", "")

    styles = _available_styles(app_dir)

    if style is None:
        click.echo(f"Current style: {click.style(current, bold=True)}\n")
        for name in styles:
            click.echo(f"  {'•' if name == current else ' '} {name}")
        return
    if style not in styles:
        raise click.BadParameter(f"choose from {', '.join(styles)}", param_hint="STYLE")

    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"
    targets = _installed_components(ui_dir)
    if not targets:
        raise click.ClickException(f"No components found in {ui_dir}")

    css_path = app_dir / config["tailwind"]["css"]
    css = css_path.read_text()
    if _SHADCN_CSS_IMPORT not in css:
        lines = css.splitlines(keepends=True)
        last_import = max(i for i, line in enumerate(lines) if line.startswith("@import"))
        lines.insert(last_import + 1, _SHADCN_CSS_IMPORT + "\n")
        css_path.write_text("".join(lines))
        click.echo(f"── Added {_SHADCN_CSS_IMPORT} to {config['tailwind']['css']}")

    config_path.write_text(
        json.dumps({**config, "style": style}, indent=4, ensure_ascii=False) + "\n"
    )

    click.echo(f"── {current} → {style}: reinstalling {len(targets)} component(s)")
    code = _shadcn(app_dir, ["add", *targets, "--overwrite", "--yes"])
    if code != 0:
        raise click.ClickException(f"shadcn-vue exited with code {code}; rerun to finish")

    click.echo(click.style(f"\n✔ Style switched to {style}", fg="green"))


@ui_group.command("list")
def ui_list() -> None:
    """Show installed shadcn-vue components."""
    app_dir = _app_dir()
    ui_dir = app_dir / "frontend" / "src" / "components" / "ui"
    components = _installed_components(ui_dir)
    if not components:
        click.echo("No components found.")
        return
    click.echo(f"{len(components)} component(s) installed:\n")
    for name in components:
        click.echo(f"  • {name}")
