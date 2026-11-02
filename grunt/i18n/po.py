"""PO / POT generation from the source-string extractor (polib-backed).

``grunt i18n extract`` regenerates ``locales/grunt.pot`` from the extractor and
merges it into every ``locales/<lang>/LC_MESSAGES/grunt.po`` (keeping existing
translations, adding new empty entries, marking removed ones obsolete).
``grunt i18n stats`` reports per-locale coverage plus how many source strings
are still Cyrillic - i.e. not yet moved to English in the code.

One translation per term: DocType metadata (``meta:`` / ``help:`` / ``hint:`` /
``select:`` / ``status:`` / ``record:`` contexts) goes into the catalogs as a
context-free entry, which ``pgettext`` falls back to - ``Name`` is translated
once, not per field of every DocType. A contextual entry stays in a locale's PO
only as an *override* whose translation differs (``Active`` -> «Активна» for a
session). Contexts written in code (``button|Save``, ``short|Jobs``) are kept.
"""

import json
import re
from collections import Counter
from pathlib import Path

import polib

from grunt.i18n.extract import extract_all
from grunt.i18n.plurals import plural_form_count

_LOCALE_DIR = Path(__file__).parent / "locales"
_GRUNT_PKG = Path(__file__).parent.parent  # …/grunt

#: Language the framework's source strings are written in. Its "coverage" is
#: really the flip progress (how many msgids are already English).
SOURCE_LOCALE = "en"


#: Metadata contexts (see grunt.i18n.meta) shared through one context-free entry.
SHARED_CONTEXTS = ("meta", "help", "hint", "select", "status", "record")


def is_shared_context(ctx: str | None) -> bool:
    prefix, sep, _ = (ctx or "").partition(":")
    return bool(sep) and prefix in SHARED_CONTEXTS


def _has_cyrillic(s: str) -> bool:
    return any("Ѐ" <= ch <= "ӿ" for ch in s or "")


_PLURAL_EXPR = {
    2: "nplurals=2; plural=(n != 1);",
    3: (
        "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : "
        "n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);"
    ),
}


def pot_path() -> Path:
    return _LOCALE_DIR / "grunt.pot"


def po_path(locale: str) -> Path:
    return _LOCALE_DIR / locale / "LC_MESSAGES" / "grunt.po"


def existing_locales() -> list[str]:
    return sorted(p.parent.parent.name for p in _LOCALE_DIR.glob("*/LC_MESSAGES/grunt.po"))


def _occurrences(row: dict) -> list[tuple[str, str]]:
    """``#:`` references - file paths only, deduped (like ``--add-location=file``).

    Line numbers would rewrite thousands of ``#:`` lines on every extract after
    any edit; the Translate app shows exact lines from the live extractor anyway.
    """
    out: list[tuple[str, str]] = []
    for token in (row.get("occurrences") or "").split(", "):
        token = token.strip()
        if not token:
            continue
        path, _, line = token.rpartition(":")
        path = path if path and line.isdigit() else token
        if (path, "") not in out:
            out.append((path, ""))
    return out


def _entry(row: dict, locale: str) -> polib.POEntry:
    kw: dict = {"msgid": row["source"], "occurrences": _occurrences(row)}
    if row.get("context"):
        kw["msgctxt"] = row["context"]
    if row.get("plural_source"):
        kw["msgid_plural"] = row["plural_source"]
        kw["msgstr_plural"] = {i: "" for i in range(plural_form_count(locale))}
    else:
        kw["msgstr"] = ""
    return polib.POEntry(**kw)


def build_pot(
    origins: tuple[str, ...] = ("grunt",),
    bench_dir: Path | None = None,
    *,
    rows: list[dict] | None = None,
) -> polib.POFile:
    """The template: one entry per (code context, source); metadata contexts
    collapse into the context-free entry (their occurrences merged)."""
    pot = polib.POFile(check_for_duplicates=False)
    pot.metadata = {
        "Project-Id-Version": "Grunt",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
    }
    if rows is None:
        rows = extract_all(bench_dir, set(origins))
    merged: dict[tuple[str, str], dict] = {}
    for row in rows:
        ctx = "" if is_shared_context(row["context"]) else row["context"]
        key = (ctx, row["source"])
        have = merged.get(key)
        if have is None:
            merged[key] = {**row, "context": ctx}
            continue
        if row.get("occurrences"):
            have["occurrences"] = ", ".join(filter(None, [have["occurrences"], row["occurrences"]]))
        if row.get("plural_source") and not have.get("plural_source"):
            have["plural_source"] = row["plural_source"]
    for key in sorted(merged):
        pot.append(_entry(merged[key], "en"))
    return pot


def merge_locale(
    locale: str,
    origins: tuple[str, ...] = ("grunt",),
    bench_dir: Path | None = None,
    *,
    rows: list[dict] | None = None,
    drop_obsolete: bool = False,
    dry_run: bool = False,
) -> dict:
    """msgmerge: keep existing msgstr, add new empty, mark obsolete removed.

    A metadata-context entry (``meta:User.email``) survives only as an override:
    its source is still there and its translation differs from the shared
    context-free one. An empty shared entry is first seeded with the most common
    translation of its contextual twins, so no translation is lost.

    ``added`` / ``removed`` list the ``(msgctxt, msgid)`` keys that this merge
    adds or newly obsoletes - the part worth reviewing before committing;
    ``overrides`` - the contextual entries kept, ``folded`` - how many were
    merged into their shared entry. *drop_obsolete* deletes ``#~``
    entries instead of keeping them (git keeps history); *dry_run* computes the
    result without writing the file.
    """
    if rows is None:
        rows = extract_all(bench_dir, set(origins))
    pot = build_pot(rows=rows)
    live = {(r["context"], r["source"]): r for r in rows if is_shared_context(r["context"])}
    path = po_path(locale)

    if path.exists():
        po = polib.pofile(str(path))
    else:
        po = polib.POFile(check_for_duplicates=False)
        po.metadata = {
            **pot.metadata,
            "Language": locale,
            "Plural-Forms": _PLURAL_EXPR.get(plural_form_count(locale), _PLURAL_EXPR[2]),
        }
    before = {_key(e) for e in po if not e.obsolete}
    contextual = [
        e for e in po if not e.obsolete and is_shared_context(e.msgctxt) and not e.msgid_plural
    ]
    po.merge(pot)
    # A hand-added entry can duplicate an existing one; polib keeps both and the
    # second translation silently wins at runtime. Keep the first, report the rest.
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for e in [e for e in po if not e.obsolete]:
        if _key(e) in seen:
            duplicates.append(_key(e))
            po.remove(e)
        seen.add(_key(e))

    shared = {e.msgid: e for e in po if not e.obsolete and not e.msgctxt and not e.msgid_plural}
    votes: dict[str, Counter] = {}
    for e in contextual:
        if e.msgstr and e.msgid in shared:
            votes.setdefault(e.msgid, Counter())[e.msgstr] += 1
    for msgid, counter in votes.items():
        if not shared[msgid].msgstr:
            shared[msgid].msgstr = counter.most_common(1)[0][0]
    overrides: list[tuple[str, str]] = []
    for e in contextual:
        row = live.get(_key(e))
        twin = shared.get(e.msgid)
        if row is not None and e.msgstr and twin is not None and e.msgstr != twin.msgstr:
            e.obsolete = False
            e.occurrences = _occurrences(row)
            overrides.append(_key(e))
        elif row is not None:
            po.remove(e)  # same as the shared entry (or empty) - nothing to keep
    # A stable order: polib appends new entries at the end, so files would drift.
    po.sort(key=lambda e: (e.obsolete, e.msgctxt or "", e.msgid))

    if drop_obsolete:
        for e in po.obsolete_entries():
            po.remove(e)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        po.save(str(path))
    after = {_key(e) for e in po if not e.obsolete}
    return {
        "path": str(path),
        "total": len(after),
        "translated": len(po.translated_entries()),
        "obsolete": len(po.obsolete_entries()),
        "added": sorted(after - before),
        # a contextual entry folded into its shared twin is not "gone from source"
        "removed": sorted(k for k in before - after if k not in live),
        "folded": len([k for k in before - after if k in live]),
        "overrides": sorted(overrides),
        "duplicates": duplicates,
    }


def _key(e: polib.POEntry) -> tuple[str, str]:
    return (e.msgctxt or "", e.msgid)


_TYPOGRAPHY = str.maketrans(
    {"…": "...", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"'}
)


def _similar_key(s: str) -> str:
    """``Attach a file…`` / ``attach a file`` / ``Attach a file:`` -> one key."""
    s = s.translate(_TYPOGRAPHY).lower().replace("colour", "color")
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"[\s.:!?]+$", "", s)


def similar(
    locale: str = "uk", origins: tuple[str, ...] = ("grunt",), bench_dir: Path | None = None
) -> list[dict]:
    """Source strings that differ only by case / trailing punctuation / typography.

    Each group is one term written several ways in the code - unify the source
    (keep punctuation in the template, not the msgid) and it is translated once.
    Groups whose translations differ in wording (not just case / punctuation)
    come first: those show in the UI as two names for one thing.
    """
    pot = build_pot(origins, bench_dir)
    path = po_path(locale)
    tr: dict[tuple[str, str], str] = {}
    if path.exists():
        tr = {_key(e): e.msgstr for e in polib.pofile(str(path)) if not e.obsolete}
    groups: dict[str, list[polib.POEntry]] = {}
    for e in pot:
        # a context written in code (``permission|read``) asks for its own wording
        if not e.msgid_plural and not e.msgctxt:
            groups.setdefault(_similar_key(e.msgid), []).append(e)
    out = []
    for entries in groups.values():
        if len(entries) < 2:
            continue
        items = [
            {
                "context": e.msgctxt or "",
                "source": e.msgid,
                "translation": tr.get(_key(e), ""),
                "files": [path for path, _line in e.occurrences],
            }
            for e in entries
        ]
        # "Yes" -> «Так» and "yes" -> «так» agree; only a different wording counts
        wordings = {_similar_key(i["translation"]) for i in items}
        out.append({"items": items, "translations": len(wordings)})
    return sorted(out, key=lambda g: (-g["translations"], g["items"][0]["source"].lower()))


def coverage(
    locale: str, origins: tuple[str, ...] = ("grunt",), bench_dir: Path | None = None
) -> dict:
    pot = build_pot(origins, bench_dir)
    path = po_path(locale)
    have: dict[tuple[str, str], bool] = {}
    if path.exists():
        for e in polib.pofile(str(path)):
            if e.obsolete:
                continue
            done = bool(e.msgstr) or bool(e.msgstr_plural and any(e.msgstr_plural.values()))
            have[(e.msgctxt or "", e.msgid)] = done

    total = translated = cyrillic = 0
    missing: list[tuple[str, str]] = []
    for e in pot:
        total += 1
        if _has_cyrillic(e.msgid):
            cyrillic += 1
        # A context-free translation covers every context via pgettext fallback.
        if have.get((e.msgctxt or "", e.msgid)) or (e.msgctxt and have.get(("", e.msgid))):
            translated += 1
        else:
            missing.append((e.msgctxt or "", e.msgid))
    return {
        "locale": locale,
        "total": total,
        "translated": translated,
        "pct": round(100 * translated / total, 1) if total else 100.0,
        "cyrillic_source": cyrillic,
        "missing": missing,
    }


# source-language flip (Ukrainian -> English in the code)
def _doctype_json_paths(module: str) -> list[Path]:
    base = _GRUNT_PKG / module / "doctypes"
    return [p for p in sorted(base.glob("*/*.json")) if p.stem == p.parent.name]


def _walk_slots(dt: dict, *, options: bool = True):
    """Yield ``(setter, msgctxt, text)`` for every translatable slot in a DocType
    dict. ``setter(new)`` mutates the dict in place. ``options=False`` skips
    Select option values - those are stored data, not captions."""
    name = dt.get("name") or ""

    def _s(obj, key):
        return lambda new: obj.__setitem__(key, new)

    if dt.get("label"):
        yield _s(dt, "label"), f"meta:{name}", dt["label"]
    if dt.get("description"):
        yield _s(dt, "description"), f"help:{name}", dt["description"]

    for fld in dt.get("fields") or []:
        fn = fld.get("fieldname") or ""
        for attr, prefix in (("label", "meta"), ("description", "help"), ("placeholder", "hint")):
            if fld.get(attr):
                yield _s(fld, attr), f"{prefix}:{name}.{fn}", fld[attr]
        if options and fld.get("fieldtype") == "Select" and isinstance(fld.get("options"), str):
            lines = fld["options"].split("\n")
            for i, line in enumerate(lines):
                if line.strip():

                    def _set_line(new, _lines=lines, _i=i, _fld=fld):
                        _lines[_i] = new
                        _fld["options"] = "\n".join(_lines)

                    yield _set_line, f"select:{name}.{fn}", line

    for si in dt.get("status_indicators") or []:
        if si.get("label"):
            yield _s(si, "label"), f"status:{name}", si["label"]


def flip_module(
    module: str, mapping: dict[str, str], *, apply: bool = False, options: bool = False
) -> dict:
    """Replace Ukrainian strings in ``grunt/<module>/doctypes/**`` with their
    English *mapping*, moving the Ukrainian into ``locales/uk/LC_MESSAGES/grunt.po``.

    Select option values are left alone unless *options* - they are what gets
    stored, so renaming them needs a data migration alongside.

    Dry-run by default. Returns ``{files, entries, unmapped}``.
    """
    po_entries: list[tuple[str, str, str]] = []  # (msgctxt, msgid_en, msgstr_uk)
    unmapped: set[str] = set()
    touched: list[str] = []

    for path in _doctype_json_paths(module):
        dt = json.loads(path.read_text())
        if "fields" not in dt:
            continue
        changed = False
        for setter, ctx, text in _walk_slots(dt, options=options):
            if not _has_cyrillic(text):
                continue
            en = mapping.get(text)
            if not en:
                unmapped.add(text)
                continue
            po_entries.append((ctx, en, text))
            if apply:
                setter(en)
                changed = True
        if changed:
            touched.append(str(path.relative_to(_GRUNT_PKG.parent)))
            path.write_text(json.dumps(dt, ensure_ascii=False, indent=2) + "\n")

    if apply and po_entries:
        _merge_uk_entries(po_entries)

    return {"files": touched, "entries": len(po_entries), "unmapped": sorted(unmapped)}


def _merge_uk_entries(entries: list[tuple[str, str, str]]) -> None:
    path = po_path("uk")
    path.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.pofile(str(path)) if path.exists() else polib.POFile(check_for_duplicates=False)
    if not pf.metadata:
        pf.metadata = {
            "Project-Id-Version": "Grunt",
            "Language": "uk",
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "Plural-Forms": _PLURAL_EXPR[3],
        }
    for ctx, msgid_en, msgstr_uk in entries:
        existing = pf.find(msgid_en, msgctxt=ctx)
        if existing is not None:
            existing.msgstr = msgstr_uk
            existing.obsolete = False
        else:
            pf.append(polib.POEntry(msgctxt=ctx, msgid=msgid_en, msgstr=msgstr_uk))
    pf.save(str(path))
