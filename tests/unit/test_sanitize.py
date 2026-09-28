"""Tests for grunt.utils.sanitize and the RichText field that applies it on write."""

from __future__ import annotations

import pytest

from grunt.metadata.field import get_field_type_class
from grunt.utils.sanitize import sanitize_html


@pytest.mark.parametrize(
    "dirty",
    [
        "<script>alert(1)</script>",
        '<img src="x" onerror="alert(1)">',
        '<a href="javascript:alert(1)">x</a>',
        '<iframe src="https://evil.example/x"></iframe>',
        '<p style="position: fixed; background: url(javascript:alert(1))">x</p>',
    ],
)
def test_strips_script_vectors(dirty):
    clean = sanitize_html(dirty)
    assert "script" not in clean
    assert "onerror" not in clean
    assert "evil.example" not in clean
    assert "position" not in clean


def test_keeps_editor_markup():
    html = (
        '<p style="margin-left: 40px">a'
        '<span style="font-family: Geist; font-size: 14px">b</span></p>'
        '<table style="min-width: 50px"><colgroup><col style="width: 120px"></colgroup>'
        '<tbody><tr><td colspan="2" rowspan="1" colwidth="120"><p>c</p></td></tr></tbody></table>'
        '<img src="/files/1.png" alt="i" loading="lazy"><a href="/app/todo/1" target="_blank">l</a>'
    )
    clean = sanitize_html(html)
    for kept in (
        "margin-left:40px",
        "font-family:Geist",
        "font-size:14px",
        "min-width:50px",
        'colspan="2"',
        'colwidth="120"',
        'src="/files/1.png"',
        'loading="lazy"',
        'href="/app/todo/1"',
        'target="_blank"',
    ):
        assert kept in clean


def test_keeps_youtube_embed_and_classes():
    html = (
        '<div class="gallery">'
        '<a class="gallery__item" href="/f/1.jpg"><img src="/f/1.jpg"></a></div>'
        '<iframe src="https://www.youtube.com/embed/abcdefghijk" allowfullscreen></iframe>'
    )
    clean = sanitize_html(html)
    assert 'class="gallery"' in clean
    assert 'class="gallery__item"' in clean
    assert 'src="https://www.youtube.com/embed/abcdefghijk"' in clean


def test_richtext_coerce_sanitizes():
    coerce = get_field_type_class("RichText").coerce
    assert coerce('<p onclick="x()">hi</p>') == "<p>hi</p>"
    assert coerce(None) is None
    assert coerce("") == ""
