"""`grunt i18n` PO/POT generation (grunt.i18n.po)."""

from __future__ import annotations

import json

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
        encoding="utf-8",
    )
    (pkg / "svc.py").write_text('from grunt.i18n import _\n_("Save changes")\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def locale_dir(tmp_path, monkeypatch):
    """Redirect po._LOCALE_DIR at an isolated dir (auto-restored)."""
    d = tmp_path / "locales"
    monkeypatch.setattr(po, "_LOCALE_DIR", d)
    return d


def test_build_pot_is_contextual_and_deduped(bench):
    pot = po.build_pot(bench_dir=bench)
    keys = {(e.msgctxt or "", e.msgid) for e in pot}
    assert ("meta:Foo", "Клієнт") in keys
    assert ("meta:Foo.nm", "Назва") in keys
    assert ("", "Save changes") in keys
    assert len(keys) == len(pot)  # no dupes


def test_coverage_counts_context_free_fallback(bench, locale_dir):
    p = po.po_path("uk")
    p.parent.mkdir(parents=True, exist_ok=True)
    pf = polib.POFile()
    pf.append(polib.POEntry(msgid="Назва", msgstr="Name"))  # context-free
    pf.save(str(p))

    c = po.coverage("uk", bench_dir=bench)

    assert c["cyrillic_source"] == 2  # Клієнт + Назва
    assert ("meta:Foo.nm", "Назва") not in c["missing"]  # covered by fallback
    assert ("meta:Foo", "Клієнт") in c["missing"]


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
    assert by[("meta:Foo", "Клієнт")].msgstr == "Client"  # kept
    assert ("meta:Foo.nm", "Назва") in by  # new, empty
    assert any(e.msgctxt == "meta:Gone" for e in merged.obsolete_entries())
    assert r["translated"] >= 1


@pytest.fixture
def flip_pkg(tmp_path, monkeypatch):
    """A fake grunt package with a `demo` module holding one DocType JSON."""
    import json as _json

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
        encoding="utf-8",
    )
    monkeypatch.setattr(po, "_GRUNT_PKG", pkg)
    monkeypatch.setattr(po, "_LOCALE_DIR", tmp_path / "locales")
    return dt_dir / "Widget.json"


def test_flip_module_dry_run_reports_unmapped(flip_pkg):
    r = po.flip_module("demo", {"Віджет": "Widget"})
    assert r["files"] == []  # dry run
    assert "Назва" in r["unmapped"] and "Чернетка" in r["unmapped"]
    assert "Віджет" not in r["unmapped"]


def test_flip_module_apply_rewrites_json_and_fills_uk_po(flip_pkg):
    import json as _json

    mapping = {"Віджет": "Widget", "Назва": "Name", "Статус": "Status",
               "Чернетка": "Draft", "Готово": "Done"}
    r = po.flip_module("demo", mapping, apply=True)
    assert r["unmapped"] == []
    assert r["entries"] == 5

    dt = _json.loads(flip_pkg.read_text(encoding="utf-8"))
    assert dt["label"] == "Widget"
    assert dt["fields"][0]["label"] == "Name"
    assert dt["fields"][1]["options"] == "Draft\nDone"

    uk = polib.pofile(str(po.po_path("uk")))
    by = {(e.msgctxt, e.msgid): e.msgstr for e in uk}
    assert by[("meta:Widget", "Widget")] == "Віджет"
    assert by[("meta:Widget.nm", "Name")] == "Назва"
    assert by[("select:Widget.st", "Draft")] == "Чернетка"

    # idempotent — second run finds nothing left to flip
    assert po.flip_module("demo", mapping, apply=True)["entries"] == 0
