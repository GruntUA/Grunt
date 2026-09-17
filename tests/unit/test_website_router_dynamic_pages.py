"""grunt.website.router._pattern_regex — matching for file-based dynamic pages.

External apps' www/ pages reach FastAPI's own route table only during ASGI
lifespan startup, *after* the "/{path:path}" catch-all is already mounted at
import time (grunt.main) — so the catch-all always matches first and shadows
them. render_page_by_route's fallback loop is what actually resolves a
dynamic ("{param}") file-based page for those apps; this covers the regex
it builds from a page's url_pattern.
"""

from __future__ import annotations

from grunt.website.router import _pattern_regex


def test_matches_single_dynamic_segment():
    rx = _pattern_regex("/service/{route}")
    m = rx.match("/service/01-01")
    assert m is not None
    assert m.groupdict() == {"route": "01-01"}


def test_does_not_match_extra_path_segments():
    rx = _pattern_regex("/service/{route}")
    assert rx.match("/service/01-01/extra") is None


def test_does_not_match_missing_segment():
    rx = _pattern_regex("/service/{route}")
    assert rx.match("/service/") is None
    assert rx.match("/service") is None


def test_literal_characters_are_escaped():
    rx = _pattern_regex("/a.b/{id}")
    assert rx.match("/aXb/1") is None
    assert rx.match("/a.b/1").groupdict() == {"id": "1"}


def test_multiple_dynamic_segments():
    rx = _pattern_regex("/office/{route}/staff/{staff_id}")
    m = rx.match("/office/cnap-01/staff/42")
    assert m.groupdict() == {"route": "cnap-01", "staff_id": "42"}
