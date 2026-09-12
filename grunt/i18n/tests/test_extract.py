"""Source-string extractor."""

from __future__ import annotations

import json

from grunt.i18n.extract import extract_all


def test_extracts_python_calls(tmp_path):
    pkg = tmp_path / "apps" / "grunt" / "grunt"
    pkg.mkdir(parents=True)
    (pkg / "x.py").write_text(
        "from grunt.i18n import _, pgettext, ngettext\n"
        '_("Hello")\n'
        'pgettext("button", "Save")\n'
        'ngettext("%(n)d item", "%(n)d items", n)\n',
        encoding="utf-8",
    )
    keyed = {(r["source"], r["context"]): r for r in extract_all(tmp_path)}

    assert keyed[("Hello", "")]["origin"] == "grunt"
    assert ("Save", "button") in keyed
    # ngettext → one plural entry, keyed by the singular msgid
    assert keyed[("%(n)d item", "")]["plural_source"] == "%(n)d items"
    assert ("%(n)d items", "") not in keyed


def test_extracts_ts_and_context_pipe(tmp_path):
    fe = tmp_path / "apps" / "grunt" / "frontend" / "src"
    fe.mkdir(parents=True)
    (fe / "C.vue").write_text(
        "<template>{{ t('World') }} {{ $t('meta:Widget.note|Нотатка') }}</template>",
        encoding="utf-8",
    )
    keyed = {(r["source"], r["context"]) for r in extract_all(tmp_path)}

    assert ("World", "") in keyed
    assert ("Нотатка", "meta:Widget.note") in keyed


def test_extracts_doctype_json(tmp_path):
    dt_dir = tmp_path / "apps" / "myapp" / "myapp" / "doctypes" / "Foo"
    dt_dir.mkdir(parents=True)
    (dt_dir / "Foo.json").write_text(
        json.dumps(
            {
                "name": "Foo",
                "label": "Фу",
                "description": "Опис типу",
                "fields": [
                    {
                        "fieldname": "s",
                        "label": "Стан",
                        "description": "Поточний стан",
                        "placeholder": "Оберіть…",
                        "fieldtype": "Select",
                        "options": "Новий\nСтарий",
                    }
                ],
                "status_indicators": [{"value": "Новий", "label": "Новий"}],
            }
        ),
        encoding="utf-8",
    )
    rows = extract_all(tmp_path)
    keyed = {(r["source"], r["context"]) for r in rows}

    assert ("Фу", "meta:Foo") in keyed
    assert ("Опис типу", "help:Foo") in keyed
    assert ("Стан", "meta:Foo.s") in keyed
    assert ("Поточний стан", "help:Foo.s") in keyed  # description → help:
    assert ("Оберіть…", "hint:Foo.s") in keyed  # placeholder → hint:
    assert ("Новий", "select:Foo.s") in keyed
    assert ("Новий", "status:Foo") in keyed
    assert all(r["origin"] == "myapp" for r in rows)


def test_skips_numbers_and_codes(tmp_path):
    dt_dir = tmp_path / "apps" / "grunt" / "grunt" / "doctypes" / "W"
    dt_dir.mkdir(parents=True)
    (dt_dir / "W.json").write_text(
        json.dumps(
            {
                "name": "W",
                "label": "Віджет",
                "fields": [
                    {
                        "fieldname": "period",
                        "label": "Період",
                        "fieldtype": "Select",
                        "options": "30d\n90d\n365d",
                    },
                    {
                        "fieldname": "coef",
                        "label": "Коеф.",
                        "fieldtype": "Select",
                        "options": "1.5\n2.0\n10",
                    },
                    {
                        "fieldname": "age",
                        "label": "Вік",
                        "fieldtype": "Select",
                        "options": "3 months\n30 days",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    sources = {r["source"] for r in extract_all(tmp_path)}

    assert "Віджет" in sources and "Період" in sources  # labels kept
    assert "3 months" in sources and "30 days" in sources  # real phrases kept
    for junk in ("30d", "90d", "365d", "1.5", "2.0", "10"):
        assert junk not in sources


def test_skips_vendor_and_test_dirs(tmp_path):
    pkg = tmp_path / "apps" / "grunt" / "grunt"
    (pkg / "node_modules").mkdir(parents=True)
    (pkg / "node_modules" / "junk.py").write_text('_("nope")', encoding="utf-8")
    (pkg / "tests").mkdir(parents=True)
    (pkg / "tests" / "test_x.py").write_text('_("also nope")', encoding="utf-8")
    keyed = {(r["source"], r["context"]) for r in extract_all(tmp_path)}

    assert ("nope", "") not in keyed
    assert ("also nope", "") not in keyed
