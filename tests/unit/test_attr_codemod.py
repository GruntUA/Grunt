"""grunt.utils.attr_codemod - finding, deciding and rewriting (pyright not run)."""

import ast

from grunt.utils.attr_codemod import (
    _Classes,
    _document_attrs,
    accepts,
    find_candidates,
    probe_source,
    rewrite_source,
)

SOURCE = """\
async def f(grunt, doc, rows):
    a = doc["status"]
    b = (await grunt.get_doc("X", "1"))["title"]
    c = doc.get("owner")
    d = doc.get("x", 1)
    doc["status"] = "Open"
    del doc["status"]
    e = doc["not-an-identifier"] + doc["_private"]
    try:
        g = doc["maybe"]
    except KeyError:
        g = None
    return [r["name"] for r in rows]


class Ctl:
    def name(self):
        return self.data.get("name")

    def other(self):
        return self.data["title"], self.data.get("note")
"""


def _by_key(cands):
    return {(c.kind, c.key, c.line) for c in cands}


def test_finds_the_rewritable_sites_only():
    found = _by_key(find_candidates(SOURCE))
    assert ("sub", "status", 2) in found
    assert ("sub", "title", 3) in found
    assert ("get", "owner", 4) in found
    assert ("sub", "status", 6) in found  # assignment
    assert ("sub", "name", 13) in found
    assert ("datasub", "title", 21) in found
    assert ("dataget", "note", 21) in found
    keys = {k for _, k, _ in found}
    assert "x" not in keys  # .get with a default
    assert "not-an-identifier" not in keys and "_private" not in keys
    assert "maybe" not in keys  # under except KeyError
    assert not any(line == 7 for _, _, line in found)  # del
    assert not any(line == 18 for _, _, line in found)  # def name(): self.data.get("name")


def test_probe_wraps_receivers_and_stays_valid_python():
    cands = find_candidates(SOURCE)
    probed = probe_source(SOURCE, cands)
    ast.parse(probed)
    assert 'reveal_type(doc, expected_text="__C0__")["status"]' in probed
    assert 'reveal_type((await grunt.get_doc("X", "1"))' not in probed  # parens stay outside
    assert 'reveal_type(await grunt.get_doc("X", "1"), expected_text=' in probed


def test_rewrite_keeps_parentheses_and_drops_data():
    cands = find_candidates(SOURCE)
    out = rewrite_source(SOURCE, cands)
    ast.parse(out)
    assert "a = doc.status" in out
    assert 'b = (await grunt.get_doc("X", "1")).title' in out
    assert "c = doc.owner" in out
    assert 'doc.status = "Open"' in out
    assert "return self.title, self.note" in out
    assert "[r.name for r in rows]" in out


def _cand(kind, key):
    source = f'x = doc["{key}"]' if kind == "sub" else f'x = doc.get("{key}")'
    return find_candidates(source)[0]


def test_accepts_by_receiver_type():
    classes = _Classes()
    classes.add(
        "class Document: ...\n"
        "class Order(Document):\n"
        "    title: str\n"
        "    note: str | None = None\n"
        "    total = 0\n"
        "    def recalc(self): ...\n"
    )
    attrs = _document_attrs()

    assert accepts(_cand("sub", "status"), "AttrDict", classes, attrs)
    assert not accepts(_cand("sub", "items"), "AttrDict", classes, attrs)  # dict method
    assert not accepts(_cand("sub", "status"), "dict[str, Any]", classes, attrs)
    assert not accepts(_cand("sub", "status"), "Any", classes, attrs)

    assert accepts(_cand("get", "title"), "Order", classes, attrs)
    assert accepts(_cand("get", "note"), "Self@Order", classes, attrs)
    assert not accepts(_cand("get", "total"), "Order", classes, attrs)  # class attribute
    assert not accepts(_cand("get", "recalc"), "Order", classes, attrs)  # method
    assert not accepts(_cand("get", "user"), "Order", classes, attrs)  # Document.user
    assert accepts(_cand("get", "name"), "Order", classes, attrs)  # same value, read only
