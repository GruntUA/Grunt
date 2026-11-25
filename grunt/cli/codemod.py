"""``grunt codemod`` - mechanical rewrites of app code, checked by pyright."""

from pathlib import Path

import click

from grunt.cli.lint import (
    _GRUNT_ROOT,
    _find_app_root,
    _find_bench_root,
    _has_pyright_config,
    _pyright_cmd,
)
from grunt.utils import attr_codemod, typed_rows_codemod


@click.group("codemod")
def codemod_group() -> None:
    """Mechanical rewrites of app code."""


def _app_roots(apps: tuple[str, ...]) -> list[Path]:
    if not apps:
        root = _find_app_root(Path.cwd())
        if root is None:
            raise click.ClickException("pyproject.toml not found: run it in an app or pass --app")
        return [root]
    bench = _find_bench_root(Path.cwd())
    if bench is None:
        raise click.ClickException("bench root not found (no apps/ with Python packages)")
    roots = [bench / "apps" / name for name in apps]
    for root in roots:
        if not (root / "pyproject.toml").exists():
            raise click.ClickException(f"app not found: {root}")
    return roots


@codemod_group.command("attr-access")
@click.option("--app", "apps", multiple=True, help="App to rewrite (repeatable; default: this one)")
@click.option("--dry-run", is_flag=True, help="Only count what would change")
def attr_access(apps: tuple[str, ...], dry_run: bool) -> None:
    """doc["field"] / doc.get("field") / doc.data["field"] -> doc.field.

    Only where pyright proves `doc` is an AttrDict (what grunt.get_doc,
    new_doc, get_list, grunt.db.get_all... return) or a DocType controller -
    a plain dict is left as it is. Run `ruff format` and the tests afterwards.
    """
    pyright = _pyright_cmd()
    if pyright is None:
        raise click.ClickException("pyright/npx not found")
    for root in _app_roots(apps):
        if not _has_pyright_config(root):
            click.echo(f"{root.name}: no pyright config - skipped")
            continue
        class_roots = list(dict.fromkeys([root, _GRUNT_ROOT]))
        result = attr_codemod.run(root, class_roots, pyright)
        if not dry_run:
            for path, text in result.files.items():
                path.write_text(text)
        verb = "would rewrite" if dry_run else "rewrote"
        click.echo(
            f"{root.name}: {verb} {result.rewrites} sites in {len(result.files)} files "
            f"({result.probed} of {result.candidates} candidates typed)"
        )
        left = ", ".join(f"{t} {n}" for t, n in result.kept.most_common(6))
        if left:
            click.echo(f"  left as is, by receiver type: {left}")


@codemod_group.command("typed-rows")
@click.option("--app", "apps", multiple=True, help="App to rewrite (repeatable; default: this one)")
@click.option(
    "--path",
    "paths",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Only the files under this path (repeatable) - pyright still checks the whole app",
)
@click.option("--dry-run", is_flag=True, help="Only count what would change")
@click.option(
    "--keep-errors",
    is_flag=True,
    help="Keep files rewritten where pyright then fails; list the errors to fix by hand",
)
def typed_rows(
    apps: tuple[str, ...], paths: tuple[Path, ...], dry_run: bool, keep_errors: bool
) -> None:
    """grunt.get_doc("Order", n) -> Order.get_doc(n), grunt.db.get_all("Order") ->
    grunt.db.get_all(Order)... - a DocType named in the code, read by its class.

    Only where pyright proves the receiver (grunt, grunt.db), the class can be
    imported without an import cycle, and the value is used as a row - see
    grunt/utils/typed_rows_codemod.py. Tests are left alone. Run `ruff check
    --fix`, `ruff format` and the tests afterwards.
    """
    pyright = _pyright_cmd()
    if pyright is None:
        raise click.ClickException("pyright/npx not found")
    roots = _app_roots(apps)
    if paths and len(roots) != 1:
        raise click.ClickException("--path takes one app")
    for root in roots:
        if not _has_pyright_config(root):
            click.echo(f"{root.name}: no pyright config - skipped")
            continue
        class_roots = list(dict.fromkeys([root, _GRUNT_ROOT]))
        result = typed_rows_codemod.Result()
        for only in [p.resolve() for p in paths] or [None]:
            part = typed_rows_codemod.run(
                root, class_roots, pyright, only=only, keep_errors=keep_errors
            )
            result.merge(part)
            if not dry_run:
                for path, text in part.files.items():
                    path.write_text(text)
        verb = "would rewrite" if dry_run else "rewrote"
        click.echo(
            f"{root.name}: {verb} {result.rewrites} of {result.candidates} sites "
            f"in {len(result.files)} files"
        )
        left = ", ".join(f"{r} {n}" for r, n in result.skipped.most_common(10))
        if left:
            click.echo(f"  left as is: {left}")
        for site in result.cycles:
            click.echo(f"  import cycle, not rewritten: {site}")
        for path, errors in result.reverted.items():
            click.echo(f"  put back (pyright): {path}")
            for e in errors[:3]:
                click.echo(f"    {e}")
        for path, errors in result.to_fix.items():
            click.echo(f"  to fix by hand (pyright): {path}")
            for e in errors:
                click.echo(f"    {e}")
