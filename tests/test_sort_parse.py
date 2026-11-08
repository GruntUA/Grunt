"""Sort.parse - "field [asc|desc]", one field, never a silent fallback."""

import pytest

from grunt.query.query import Sort


@pytest.mark.parametrize(
    ("spec", "order", "expected"),
    [
        ("title", "desc", Sort("title", descending=True)),
        ("title", "asc", Sort("title", descending=False)),
        ("title", "ASC", Sort("title", descending=False)),
        ("title asc", "desc", Sort("title", descending=False)),
        ("  title   DESC ", "asc", Sort("title", descending=True)),
    ],
)
def test_parse(spec, order, expected):
    assert Sort.parse(spec, order) == expected


@pytest.mark.parametrize("spec", ["", "a, b", "a asc, b", "a,b", "a up", "a asc desc"])
def test_malformed(spec):
    with pytest.raises(ValueError):
        Sort.parse(spec)


def test_bad_order():
    with pytest.raises(ValueError):
        Sort.parse("title", "up")


def test_unknown_field_only_when_known_given():
    assert Sort.parse("creation") == Sort("creation")
    with pytest.raises(ValueError, match="creation"):
        Sort.parse("creation", known={"created_at"})
