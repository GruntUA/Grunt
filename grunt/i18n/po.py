"""PO / POT generation from the source-string extractor (polib-backed).

``grunt i18n extract`` regenerates ``locales/grunt.pot`` from the extractor and
merges it into every ``locales/<lang>/LC_MESSAGES/grunt.po`` (keeping existing
translations, adding new empty entries, marking removed ones obsolete).
``grunt i18n stats`` reports per-locale coverage plus how many source strings
are still Cyrillic — i.e. not yet moved to English in the code.
"""

from __future__ import annotations

import json
from pathlib import Path

import polib

from grunt.i18n.extract import extract_all
from grunt.i18n.plurals import plural_form_count

_LOCALE_DIR = Path(__file__).parent / "locales"
_GRUNT_PKG = Path(__file__).parent.parent  # …/grunt

#: Language the framework's source strings are written in. Its "coverage" is
#: really the flip progress (how many msgids are already English).
SOURCE_LOCALE = "en"


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
    out: list[tuple[str, str]] = []
    for token in (row.get("occurrences") or "").split(", "):
        token = token.strip()
        if not token:
            continue
        path, _, line = token.rpartition(":")
        out.append((path or token, line if line.isdigit() else ""))
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


def build_pot(origins: tuple[str, ...] = ("grunt",), bench_dir: Path | None = None) -> polib.POFile:
    pot = polib.POFile(check_for_duplicates=False)
    pot.metadata = {
        "Project-Id-Version": "Grunt",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
    }
    seen: set[tuple[str, str]] = set()
    rows = extract_all(bench_dir, set(origins))
    for row in sorted(rows, key=lambda r: (r["context"], r["source"])):
        key = (row["context"], row["source"])
        if key in seen:
            continue
        seen.add(key)
        pot.append(_entry(row, "en"))
    return pot


def merge_locale(
    locale: str, origins: tuple[str, ...] = ("grunt",), bench_dir: Path | None = None
) -> dict:
    """msgmerge: keep existing msgstr, add new empty, mark obsolete removed."""
    pot = build_pot(origins, bench_dir)
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
    po.merge(pot)
    path.parent.mkdir(parents=True, exist_ok=True)
    po.save(str(path))
    return {
        "path": str(path),
        "total": len([e for e in po if not e.obsolete]),
        "translated": len(po.translated_entries()),
        "obsolete": len(po.obsolete_entries()),
    }


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


# ── source-language flip (Ukrainian → English in the code) ──────────────────
def _doctype_json_paths(module: str) -> list[Path]:
    base = _GRUNT_PKG / module / "doctypes"
    return [p for p in sorted(base.glob("*/*.json")) if p.stem == p.parent.name]


def _walk_slots(dt: dict, *, options: bool = True):
    """Yield ``(setter, msgctxt, text)`` for every translatable slot in a DocType
    dict. ``setter(new)`` mutates the dict in place. ``options=False`` skips
    Select option values — those are stored data, not captions."""
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

    Select option values are left alone unless *options* — they are what gets
    stored, so renaming them needs a data migration alongside.

    Dry-run by default. Returns ``{files, entries, unmapped}``.
    """
    po_entries: list[tuple[str, str, str]] = []  # (msgctxt, msgid_en, msgstr_uk)
    unmapped: set[str] = set()
    touched: list[str] = []

    for path in _doctype_json_paths(module):
        dt = json.loads(path.read_text(encoding="utf-8"))
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
            path.write_text(json.dumps(dt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
            existing.obsolete = 0
        else:
            pf.append(polib.POEntry(msgctxt=ctx, msgid=msgid_en, msgstr=msgstr_uk))
    pf.save(str(path))
