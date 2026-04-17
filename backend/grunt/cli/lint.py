import shutil
import subprocess
from pathlib import Path

import click


def _find_app_root(start: Path) -> Path:
    """Walk up from start to find the nearest directory with pyproject.toml."""
    for directory in [start.resolve(), *start.resolve().parents]:
        if (directory / "pyproject.toml").exists():
            return directory
    return Path(__file__).parents[3]


def _print_status(name: str, ok: bool) -> None:
    if ok:
        click.echo(click.style(f"  ✓ {name}: OK\n", fg="green"))
    else:
        click.echo(click.style(f"  ✗ {name}: є помилки\n", fg="red"))


def _run_python(root: Path, fix: bool) -> int:
    if shutil.which("ruff") is None:
        click.echo(click.style("  [skip] ruff не встановлено", fg="yellow"))
        return 0

    backend = root / "backend"
    results = []

    click.echo(click.style("── ruff check ──", bold=True))
    cmd = ["ruff", "check", str(backend)]
    if fix:
        cmd.append("--fix")
    results.append(subprocess.run(cmd, cwd=root).returncode)

    click.echo(click.style("── ruff format ──", bold=True))
    cmd = ["ruff", "format", str(backend)]
    if not fix:
        cmd.append("--check")
    results.append(subprocess.run(cmd, cwd=root).returncode)

    ok = all(r == 0 for r in results)
    _print_status("Python (ruff)", ok)
    return 0 if ok else 1


def _run_frontend(root: Path) -> int:
    if not (root / "package.json").exists():
        click.echo(click.style("  [skip] package.json не знайдено", fg="yellow"))
        return 0

    if shutil.which("npm") is None:
        click.echo(click.style("  [skip] npm не знайдено", fg="yellow"))
        return 0

    click.echo(click.style("── vue-tsc ──", bold=True))
    pm = (
        "pnpm"
        if (root / "pnpm-lock.yaml").exists()
        else "yarn"
        if (root / "yarn.lock").exists()
        else "npm"
    )
    result = subprocess.run([pm, "run", "typecheck"], cwd=root)
    ok = result.returncode == 0
    _print_status("TypeScript/Vue (vue-tsc)", ok)
    return result.returncode


@click.command("lint")
@click.option("--fix", is_flag=True, help="Автоматично виправити (ruff --fix + ruff format)")
@click.option("--py", "only_py", is_flag=True, help="Тільки Python")
@click.option("--js", "only_js", is_flag=True, help="Тільки TypeScript/Vue")
@click.option("--path", default=None, help="Корінь проєкту (авто-пошук за замовчуванням)")
def lint(fix: bool, only_py: bool, only_js: bool, path: str | None) -> None:
    """Перевірити код на стандарти: ruff (Python) + vue-tsc (TS/Vue)."""
    root = Path(path).resolve() if path else _find_app_root(Path.cwd())

    if not (root / "pyproject.toml").exists():
        click.echo(click.style(f"[error] pyproject.toml не знайдено в: {root}", fg="red"), err=True)
        raise SystemExit(1)

    click.echo(f"Проєкт: {root}\n")

    codes: list[int] = []

    if not only_js:
        codes.append(_run_python(root, fix))

    if not only_py:
        codes.append(_run_frontend(root))

    if any(c != 0 for c in codes):
        click.echo(click.style("Є помилки.", fg="red", bold=True))
        raise SystemExit(1)
    else:
        click.echo(click.style("Все гаразд.", fg="green", bold=True))
