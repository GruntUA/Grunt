"""`grunt i18n` - framework translation catalogs (PO/POT)."""

import json
from pathlib import Path

import click

lazy from grunt.i18n import po
lazy from grunt.i18n.extract import extract_all


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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show which strings would be added / obsoleted per locale; write nothing.",
)
@click.option(
    "--no-obsolete",
    is_flag=True,
    help="Delete obsolete (#~) entries instead of keeping them in the catalogs.",
)
@click.option(
    "--verbose", "-v", is_flag=True, help="List every added / obsoleted / override string."
)
def extract_cmd(locales: tuple[str, ...], dry_run: bool, no_obsolete: bool, verbose: bool) -> None:
    """Regenerate grunt.pot from the source; optionally msgmerge locale catalogs.

    Strings whose source is gone (e.g. a removed DocType's labels and Select
    options) become obsolete; run with --dry-run first to review them.
    """

    rows = extract_all(origins={"grunt"})
    pot = po.build_pot(rows=rows)
    if not dry_run:
        po.pot_path().parent.mkdir(parents=True, exist_ok=True)
        pot.save(str(po.pot_path()))
    click.echo(f"grunt.pot — {len(pot)} strings → {po.pot_path()}{' (dry run)' if dry_run else ''}")

    limit = None if verbose else 15
    for loc in locales:
        r = po.merge_locale(loc, rows=rows, drop_obsolete=no_obsolete, dry_run=dry_run)
        obsolete = f", {r['obsolete']} obsolete" if r["obsolete"] else ""
        click.echo(f"  {loc:6} {r['translated']}/{r['total']} translated{obsolete} → {r['path']}")
        click.echo(
            f"         +{len(r['added'])} new, -{len(r['removed'])} no longer in source, "
            f"{len(r['overrides'])} context overrides"
            + (f", {r['folded']} folded into shared entries" if r["folded"] else "")
        )
        for ctx, msg in r["duplicates"]:
            click.echo(f"      ! duplicate dropped (kept the first): {(ctx or '—')} {msg[:70]}")
        if dry_run or verbose:
            for sign, keys in (("+", r["added"]), ("-", r["removed"]), ("~", r["overrides"])):
                for ctx, msg in keys[:limit]:
                    click.echo(f"      {sign} {(ctx or '—'):40} {msg[:70]}")
                if limit is not None and len(keys) > limit:
                    click.echo(f"      {sign} … +{len(keys) - limit} more (-v to list all)")


@i18n_group.command("similar")
@click.option(
    "--locale", "-l", default="uk", show_default=True, help="Show this locale's translations."
)
@click.option("--files", is_flag=True, help="Also list the files each variant comes from.")
@click.option("--all", "show_all", is_flag=True, help="Also groups already translated the same.")
def similar_cmd(locale: str, files: bool, show_all: bool) -> None:
    """Source strings written several ways (case, trailing ':' / '…', dashes).

    Unify each group in the code to one msgid; punctuation belongs in the template.
    """

    groups = po.similar(locale)
    for g in groups:
        if g["translations"] == 1 and not show_all:
            continue
        mark = "≠" if g["translations"] > 1 else "="
        click.echo(mark)
        for i in g["items"]:
            ctx = f"[{i['context']}] " if i["context"] else ""
            click.echo(f"  {ctx}{i['source'][:60]!r:62} → {i['translation'][:40]}")
            if files:
                for f in i["files"][:5]:
                    click.echo(f"      {f}")
    differ = sum(1 for g in groups if g["translations"] > 1)
    extra = sum(len(g["items"]) - 1 for g in groups)
    click.echo(
        f"\n{len(groups)} groups, {extra} extra msgids; {differ} translated inconsistently (≠)"
    )


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

    mapping: dict[str, str] = {}
    if map_path:
        mapping = json.loads(Path(map_path).read_text())

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
