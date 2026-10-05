"""`grunt i18n` - framework translation catalogs (PO/POT)."""

from __future__ import annotations

import json
from pathlib import Path

import click


@click.group("i18n")
def i18n_group() -> None:
    """Translation catalogs for the framework (``grunt/i18n/locales``)."""


@i18n_group.command("extract")
@click.option(
    "--locale",
    "-l",
    "locales",
    multiple=True,
    help="msgmerge grunt.pot into these locale catalogs (keeps translations, "
    "marks removed strings obsolete). Omit to only regenerate grunt.pot.",
)
def extract_cmd(locales: tuple[str, ...]) -> None:
    """Regenerate grunt.pot from the source; optionally msgmerge locale catalogs."""
    from grunt.i18n import po

    pot = po.build_pot()
    po.pot_path().parent.mkdir(parents=True, exist_ok=True)
    pot.save(str(po.pot_path()))
    click.echo(f"grunt.pot — {len(pot)} strings → {po.pot_path()}")

    for loc in locales:
        r = po.merge_locale(loc)
        obsolete = f", {r['obsolete']} obsolete" if r["obsolete"] else ""
        click.echo(f"  {loc:6} {r['translated']}/{r['total']} translated{obsolete} → {r['path']}")


@i18n_group.command("stats")
@click.option("--locale", "-l", "locales", multiple=True)
@click.option("--show-missing", is_flag=True, help="List untranslated strings.")
@click.option(
    "--fail-under",
    type=float,
    default=None,
    help="Exit non-zero if the worst locale is below this percentage.",
)
def stats_cmd(locales: tuple[str, ...], show_missing: bool, fail_under: float | None) -> None:
    """Coverage per locale + how many source strings are still Cyrillic."""
    from grunt.i18n import po

    targets = list(locales) or sorted({po.SOURCE_LOCALE, *po.existing_locales(), "uk"})
    worst = 100.0
    for loc in targets:
        c = po.coverage(loc)
        if loc == po.SOURCE_LOCALE:
            flipped = c["total"] - c["cyrillic_source"]
            pct = round(100 * flipped / c["total"], 1) if c["total"] else 100.0
            click.echo(
                f"{loc:6} source — flipped to English {flipped}/{c['total']} ({pct}%), "
                f"still Cyrillic: {c['cyrillic_source']}"
            )
        else:
            click.echo(f"{loc:6} translated {c['translated']}/{c['total']} ({c['pct']}%)")
            worst = min(worst, c["pct"])
        if show_missing:
            for ctx, msg in c["missing"][:80]:
                click.echo(f"    {(ctx or '—'):32} {msg}")
            if len(c["missing"]) > 80:
                click.echo(f"    … +{len(c['missing']) - 80} more")

    if fail_under is not None and worst < fail_under:
        raise SystemExit(f"i18n coverage {worst:.1f}% < required {fail_under}%")


@i18n_group.command("flip")
@click.argument("module")
@click.option(
    "--map",
    "map_path",
    type=click.Path(exists=True, dir_okay=False),
    help="JSON object {ukrainian: english}.",
)
@click.option("--apply", is_flag=True, help="Write the changes (default: dry-run).")
@click.option(
    "--options",
    "options",
    is_flag=True,
    help="Also rename Select option values (stored data — migrate existing rows too).",
)
def flip_cmd(module: str, map_path: str | None, apply: bool, options: bool) -> None:
    """Flip a module's DocType JSON to English; move Ukrainian into uk/grunt.po.

    Run without --map to list the strings that need translating. Provide those in
    a JSON map, re-run with --apply, then `grunt i18n extract -l uk -l en`.
    """
    from grunt.i18n import po

    mapping: dict[str, str] = {}
    if map_path:
        mapping = json.loads(Path(map_path).read_text(encoding="utf-8"))

    r = po.flip_module(module, mapping, apply=apply, options=options)

    if r["unmapped"]:
        click.echo(f"# {len(r['unmapped'])} strings still need an English mapping:")
        for s in r["unmapped"]:
            click.echo(json.dumps(s, ensure_ascii=False))
        click.echo("")

    verb = "flipped" if apply else "would flip"
    click.echo(f"{verb} {r['entries']} strings in {len(r['files'])} files")
    if apply and r["files"]:
        click.echo(
            "next: grunt i18n extract   (regenerate grunt.pot)\n"
            "      grunt doctype sync <DocType…>   (re-register the flipped metadata)\n"
            "      restart the server"
        )
