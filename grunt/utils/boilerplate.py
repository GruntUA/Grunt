"""
Grunt App Boilerplate Generator.

Provides interactive scaffolding for new Grunt applications.
Called by: grunt create-app <name>
"""

from __future__ import annotations

import email.headerregistry
import json
import re
import subprocess
from typing import TYPE_CHECKING

import click

from grunt.utils.codegen import render_template

if TYPE_CHECKING:
    from pathlib import Path


# Validation


def is_valid_app_name(name: str) -> bool:
    """App name must be snake_case and start with a letter."""
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def is_valid_email(addr: str) -> bool:
    """Validate email address format."""
    try:
        email.headerregistry.Address(addr_spec=addr)
        return "@" in addr
    except Exception:
        return False


# Public entry point


def make_boilerplate(dest: Path, app_name: str, no_git: bool = False) -> None:
    """Interactively create a new Grunt app at dest/app_name."""
    if not is_valid_app_name(app_name):
        click.echo(
            "Error: the app name must be snake_case "
            "(lowercase letters, digits and underscores only; starting with a letter).",
            err=True,
        )
        raise SystemExit(1)

    hooks = _get_user_inputs(app_name)
    _create_app_boilerplate(dest, hooks, no_git=no_git)


# Interactive prompts


def _prompt_validated(
    prompt_text: str, validator, error_msg: str, default: str | None = None
) -> str:
    """Re-prompt until the value passes validation."""
    while True:
        value = (
            click.prompt(prompt_text, default=default)
            if default is not None
            else click.prompt(prompt_text)
        )
        if validator(value):
            return value
        click.echo(f"  ! {error_msg}", err=True)


def _get_user_inputs(app_name: str) -> dict:
    """Gather app configuration interactively."""
    default_title = app_name.replace("_", " ").title()
    default_module = app_name

    click.echo(f"\n  New Grunt app: {app_name}\n")

    title = _prompt_validated(
        "Title",
        validator=lambda v: bool(v.strip()),
        error_msg="The title cannot be empty.",
        default=default_title,
    )

    description = click.prompt("Description", default=f"{title} — Grunt app")

    author = click.prompt("Author (name or organization)")

    email = _prompt_validated(
        "Author email",
        validator=is_valid_email,
        error_msg="Invalid email format.",
    )

    version = click.prompt("Version", default="0.1.0")
    icon = click.prompt("Icon (emoji)", default="📦")
    color = click.prompt("Accent color (hex)", default="#2D6A4F")

    module = _prompt_validated(
        "Module name (snake_case)",
        validator=lambda v: bool(re.match(r"^[a-z][a-z0-9_]*$", v)),
        error_msg="The module name must be snake_case.",
        default=default_module,
    )

    use_git = click.confirm("\nInitialize a git repository?", default=True)

    return {
        "app_name": app_name,
        "title": title,
        "description": description,
        "author": author,
        "email": email,
        "version": version,
        "icon": icon,
        "color": color,
        "module": module,
        "use_git": use_git,
    }


# Directory scaffold


def _create_app_boilerplate(dest: Path, hooks: dict, no_git: bool = False) -> None:
    """Build the full app directory structure."""
    app_name: str = hooks["app_name"]
    module: str = hooks["module"]
    app_dir = dest / app_name

    if app_dir.exists():
        click.echo(f"Error: directory '{app_dir}' already exists.", err=True)
        raise SystemExit(1)

    # Create directories
    for subdir in [
        app_dir / module / "doctypes",
        app_dir / module / "fixtures",
        app_dir / module / "templates",
    ]:
        subdir.mkdir(parents=True)

    # Write files
    _write_grunt_app_py(app_dir, module, hooks)
    _write_app_json(app_dir, module, hooks)
    _write_install_py(app_dir, hooks)
    _write_readme(app_dir, hooks)
    _write_gitignore(app_dir)
    _write_module_init(app_dir, module, hooks)
    _write_hooks_py(app_dir, module, hooks)
    _write_tasks_py(app_dir, module, hooks)
    _write_routes_py(app_dir, module, hooks)
    _write_doctypes_init(app_dir, module)
    _write_fixtures_init(app_dir, module)
    _write_workspace_fixture(app_dir, module, hooks)
    _write_jsconfig(app_dir, module)
    _write_types_dts(app_dir, module)

    # Git
    if not no_git and hooks.get("use_git", True):
        _init_git(app_dir)

    # Summary
    click.echo(f"\n✓ App '{app_name}' created in {app_dir}/")
    click.echo("\nStructure:")
    for p in sorted(app_dir.rglob("*")):
        if not p.is_dir() and ".git" not in str(p):
            rel = p.relative_to(app_dir.parent)
            click.echo(f"  {rel}")

    click.echo("\nNext steps:")
    click.echo(f"  grunt app install {app_name}")
    click.echo("  grunt serve --reload")


# File writers


def _write_grunt_app_py(app_dir: Path, module: str, h: dict) -> None:
    (app_dir / "grunt_app.py").write_text(
        render_template("app/app.py.jinja", {**h, "module": module}),
        encoding="utf-8",
    )


def _write_app_json(app_dir: Path, module: str, h: dict) -> None:
    data = {
        "name": h["app_name"],
        "title": h["title"],
        "version": h["version"],
        "description": h["description"],
        "author": h["author"],
        "email": h["email"],
        "icon": h["icon"],
        "color": h["color"],
        "modules": [module],
        "depends_on": [],
    }
    (app_dir / "app.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_install_py(app_dir: Path, h: dict) -> None:
    (app_dir / "install.py").write_text(
        render_template("app/install.py.jinja", h),
        encoding="utf-8",
    )


def _write_readme(app_dir: Path, h: dict) -> None:
    (app_dir / "README.md").write_text(
        render_template("app/README.md.jinja", h),
        encoding="utf-8",
    )


def _write_gitignore(app_dir: Path) -> None:
    (app_dir / ".gitignore").write_text(
        render_template("app/.gitignore.jinja", {}),
        encoding="utf-8",
    )


def _write_module_init(app_dir: Path, module: str, h: dict) -> None:
    (app_dir / module / "__init__.py").write_text(
        f'''"""Module {module} for {h["title"]}."""\n''',
        encoding="utf-8",
    )


def _write_hooks_py(app_dir: Path, module: str, h: dict) -> None:
    (app_dir / module / "hooks.py").write_text(
        render_template("app/hooks.py.jinja", h),
        encoding="utf-8",
    )


def _write_tasks_py(app_dir: Path, module: str, h: dict) -> None:
    (app_dir / module / "tasks.py").write_text(
        render_template("app/tasks.py.jinja", h),
        encoding="utf-8",
    )


def _write_routes_py(app_dir: Path, module: str, h: dict) -> None:
    (app_dir / module / "routes.py").write_text(
        render_template("app/routes.py.jinja", h),
        encoding="utf-8",
    )


def _write_doctypes_init(app_dir: Path, module: str) -> None:
    (app_dir / module / "doctypes" / "__init__.py").write_text("", encoding="utf-8")


def _write_fixtures_init(app_dir: Path, module: str) -> None:
    (app_dir / module / "fixtures" / "__init__.py").write_text("", encoding="utf-8")


def _write_workspace_fixture(app_dir: Path, module: str, h: dict) -> None:
    data = [
        {
            "name": h["app_name"],
            "label": h["title"],
            "icon": h["icon"],
            "color": h["color"],
            "description": h["description"],
            "items": [],
        }
    ]
    (app_dir / module / "fixtures" / "00_workspace.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsconfig(app_dir: Path, module: str) -> None:
    (app_dir / "jsconfig.json").write_text(
        render_template("app/jsconfig.json.jinja", {"module": module}),
        encoding="utf-8",
    )


def _write_types_dts(app_dir: Path, module: str) -> None:
    (app_dir / module / "types.d.ts").write_text(
        render_template("app/types.d.ts.jinja", {}),
        encoding="utf-8",
    )


# Git


def _init_git(app_dir: Path) -> None:
    try:
        subprocess.run(["git", "init", str(app_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(app_dir), "add", "."],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(app_dir), "commit", "-m", "Initial commit (grunt create-app)"],
            check=True,
            capture_output=True,
        )
        click.echo("  git: repository initialized with an initial commit.")
    except subprocess.CalledProcessError as exc:
        click.echo(f"  git: initialization failed: {exc}", err=True)
    except FileNotFoundError:
        click.echo("  git: not found, skipping.", err=True)
