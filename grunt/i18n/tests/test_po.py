"""`grunt i18n` PO/POT generation (grunt.i18n.po)."""

import json
import json as _json

import polib
import pytest

from grunt.i18n import po


@pytest.fixture
def bench(tmp_path):
    """A fake bench: apps/grunt/grunt with one DocType JSON + one .py."""
    pkg = tmp_path / "apps" / "grunt" / "grunt"
    (pkg / "doctypes" / "Foo").mkdir(parents=True)
    (pkg / "doctypes" / "Foo" / "Foo.json").write_text(
        json.dumps(
            {
                "name": "Foo",
                "label": "Клієнт",
                "fields": [{"fieldname": "nm", "label": "Назва", "fieldtype": "Data"}],
            }
        ),
    )
    (pkg / "svc.py").write_text('from grunt.i18n import _\n_("Save changes")\n')
    return tmp_path


@pytest.fixture
def locale_dir(tmp_path, monkeypatch):
    """Redirect po._LOCALE_DIR at an isolated dir (auto-restored)."""
    d = tmp_path / "locales"
    monkeypatch.setattr(po, "_LOCALE_DIR", d)
    return d


def test_build_pot_shares_metadata_strings(bench):
    pot = po.build_pot(bench_dir=bench)
    keys = {(e.msgctxt or "", e.msgid) for e in pot}
    # meta:Foo / meta:Foo.nm collapse into context-free entries
    assert keys == {("", "Клієнт"), ("", "Назва"), ("", "Save changes")}
    assert len(keys) == len(pot)  # no dupes


def test_build_pot_keeps_code_contexts_and_merges_occurrences():
    rows = [
        {"source": "Name", "context": "meta:A.nm", "occurrences": "a/A.json"},
        {"source": "Name", "context": "meta:B.nm", "occurrences": "b/B.json"},
        {"source": "Name", "context": "", "occurrences": "x.py:3"},
        {"source": "Save", "context": "button", "occurrences": "y.vue:9"},
    ]
    pot = po.build_pot(rows=rows)
    by = {(e.msgctxt or "", e.msgid): e for e in pot}
    assert set(by) == {("", "Name"), ("button", "Save")}
    assert by[("", "Name")].occurrences == [("a/A.json", ""), ("b/B.json", ""), ("x.py", "")]


def test_coverage_counts_context_free_fallback(bench, locale_dir):
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgid="Назва", msgstr="Name"))  # context-free
    pf.save(str(p))

    c = po.coverage("uk", bench_dir=bench)

    assert c["cyrillic_source"] == 2  # Клієнт + Назва
    assert ("", "Назва") not in c["missing"]
    assert ("", "Клієнт") in c["missing"]


def test_merge_locale_keeps_translations_and_marks_obsolete(bench, locale_dir):
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgctxt="meta:Foo", msgid="Клієнт", msgstr="Client"))
    pf.append(polib.POEntry(msgctxt="meta:Gone", msgid="Старе", msgstr="Old"))
    pf.save(str(p))

    r = po.merge_locale("uk", bench_dir=bench)

    merged = polib.pofile(str(p))
    by = {(e.msgctxt or "", e.msgid): e for e in merged if not e.obsolete}
    assert by[("", "Клієнт")].msgstr == "Client"  # folded into the shared entry
    assert ("meta:Foo", "Клієнт") not in by
    assert ("", "Назва") in by  # new, empty
    assert any(e.msgctxt == "meta:Gone" for e in merged.obsolete_entries())
    assert r["translated"] >= 1
    assert r["removed"] == [("meta:Gone", "Старе")]
    assert r["folded"] == 1
    assert ("", "Назва") in r["added"]


def test_merge_locale_keeps_differing_context_as_override(bench, locale_dir):
    (bench / "apps" / "grunt" / "grunt" / "doctypes" / "Bar").mkdir()
    (bench / "apps" / "grunt" / "grunt" / "doctypes" / "Bar" / "Bar.json").write_text(
        json.dumps({"name": "Bar", "fields": [{"fieldname": "a", "label": "Назва"}]})
    )
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgctxt="meta:Foo.nm", msgid="Назва", msgstr="Name"))
    pf.append(polib.POEntry(msgctxt="meta:Bar.a", msgid="Назва", msgstr="Title"))
    pf.append(polib.POEntry(msgctxt="meta:Bar.a", msgid="Клієнт", msgstr=""))
    pf.save(str(p))

    r = po.merge_locale("uk", bench_dir=bench)

    by = {(e.msgctxt or "", e.msgid): e.msgstr for e in polib.pofile(str(p)) if not e.obsolete}
    assert by[("", "Назва")] in ("Name", "Title")  # seeded from the twins
    other = "Title" if by[("", "Назва")] == "Name" else "Name"
    ctx = "meta:Bar.a" if other == "Title" else "meta:Foo.nm"
    assert by[(ctx, "Назва")] == other  # the differing one stays as an override
    assert r["overrides"] == [(ctx, "Назва")]


def test_merge_locale_dry_run_and_drop_obsolete(bench, locale_dir):
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgctxt="meta:Gone", msgid="Старе", msgstr="Old"))
    pf.save(str(p))
    original = p.read_text()

    r = po.merge_locale("uk", bench_dir=bench, dry_run=True)
    assert p.read_text() == original  # nothing written
    assert r["removed"] == [("meta:Gone", "Старе")]

    po.merge_locale("uk", bench_dir=bench, drop_obsolete=True)
    assert not polib.pofile(str(p)).obsolete_entries()


def test_merge_locale_drops_duplicate_entries(bench, locale_dir):
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile(check_for_duplicates=False)
    pf.append(polib.POEntry(msgid="Save changes", msgstr="Зберегти зміни"))
    pf.append(polib.POEntry(msgid="Save changes", msgstr="Зберегти"))
    pf.save(str(p))

    r = po.merge_locale("uk", bench_dir=bench)

    kept = [e for e in polib.pofile(str(p)) if e.msgid == "Save changes"]
    assert [e.msgstr for e in kept] == ["Зберегти зміни"]
    assert r["duplicates"] == [("", "Save changes")]


def test_pot_references_are_file_only(bench):
    (bench / "apps" / "grunt" / "grunt" / "svc.py").write_text(
        'from grunt.i18n import _\n_("Save changes")\n\n_("Save changes")\n'
    )
    pot = po.build_pot(bench_dir=bench)
    entry = next(e for e in pot if e.msgid == "Save changes")
    assert entry.occurrences == [("grunt/grunt/svc.py", "")]  # no line numbers, deduped


@pytest.fixture
def flip_pkg(tmp_path, monkeypatch):
    """A fake grunt package with a `demo` module holding one DocType JSON."""
    pkg = tmp_path / "grunt"
    dt_dir = pkg / "demo" / "doctypes" / "Widget"
    dt_dir.mkdir(parents=True)
    (dt_dir / "Widget.json").write_text(
        _json.dumps(
            {
                "name": "Widget",
                "label": "Віджет",
                "fields": [
                    {"fieldname": "nm", "label": "Назва", "fieldtype": "Data"},
                    {
                        "fieldname": "st",
                        "label": "Статус",
                        "fieldtype": "Select",
                        "options": "Чернетка\nГотово",
                    },
                ],
            }
        ),
    )
    monkeypatch.setattr(po, "_GRUNT_PKG", pkg)
    monkeypatch.setattr(po, "_LOCALE_DIR", tmp_path / "locales")
    return dt_dir / "Widget.json"


def test_flip_module_dry_run_reports_unmapped(flip_pkg):
    r = po.flip_module("demo", {"Віджет": "Widget"}, options=True)
    assert r["files"] == []  # dry run
    assert "Назва" in r["unmapped"] and "Чернетка" in r["unmapped"]
    assert "Віджет" not in r["unmapped"]


def test_flip_module_apply_rewrites_json_and_fills_uk_po(flip_pkg):
    mapping = {
        "Віджет": "Widget",
        "Назва": "Name",
        "Статус": "Status",
        "Чернетка": "Draft",
        "Готово": "Done",
    }
    r = po.flip_module("demo", mapping, apply=True, options=True)
    assert r["unmapped"] == []
    assert r["entries"] == 5

    dt = _json.loads(flip_pkg.read_text())
    assert dt["label"] == "Widget"
    assert dt["fields"][0]["label"] == "Name"
    assert dt["fields"][1]["options"] == "Draft\nDone"

    uk = polib.pofile(str(po.po_path("uk")))
    by = {(e.msgctxt, e.msgid): e.msgstr for e in uk}
    assert by[("meta:Widget", "Widget")] == "Віджет"
    assert by[("meta:Widget.nm", "Name")] == "Назва"
    assert by[("select:Widget.st", "Draft")] == "Чернетка"

    # idempotent - second run finds nothing left to flip
    assert po.flip_module("demo", mapping, apply=True, options=True)["entries"] == 0


def test_flip_module_leaves_select_values_by_default(flip_pkg):
    r = po.flip_module(
        "demo", {"Віджет": "Widget", "Назва": "Name", "Статус": "Status"}, apply=True
    )
    assert r["unmapped"] == []  # option values are not even asked for
    dt = _json.loads(flip_pkg.read_text())
    assert dt["fields"][1]["label"] == "Status"
    assert dt["fields"][1]["options"] == "Чернетка\nГотово"  # stored values untouched


def test_similar_groups_spelling_variants(bench, locale_dir):
    (bench / "apps" / "grunt" / "grunt" / "svc.py").write_text(
        'from grunt.i18n import _\n_("Attach a file")\n_("attach a file…")\n_("Save")\n'
    )
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgid="Attach a file", msgstr="Прикріпити файл"))
    pf.append(polib.POEntry(msgid="attach a file…", msgstr="прикріпити файл…"))
    pf.save(str(p))

    groups = po.similar("uk", bench_dir=bench)

    assert [sorted(i["source"] for i in g["items"]) for g in groups] == [
        ["Attach a file", "attach a file…"]
    ]
    assert groups[0]["translations"] == 1  # same wording - case / "…" ignored
