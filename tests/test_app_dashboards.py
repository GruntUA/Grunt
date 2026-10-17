"""An app's home offers every Page of the app the user may open as a dashboard."""

from types import SimpleNamespace

from grunt.api.v1.dashboard import page_visible
from grunt.api.v1.workspace import _dashboards


def _user(*roles: str) -> SimpleNamespace:
    return SimpleNamespace(roles=list(roles))


def test_page_visible_needs_publishing_and_a_listed_role():
    page = {"is_published": 1, "roles": "Accountant, Auditor"}
    assert page_visible(page, _user("Auditor"))
    assert not page_visible(page, _user("Clerk"))
    assert page_visible({"is_published": 1, "roles": ""}, _user("Clerk"))
    assert not page_visible({"is_published": 0}, _user("Clerk"))
    assert page_visible({"is_published": 0, "roles": "Nobody"}, _user("System Manager"))


def test_dashboards_put_the_home_page_first():
    pages = [
        {"name": "a-stats", "label": "Stats", "app": "acme"},
        {"name": "a-home", "label": "Home", "app": None},
        {"name": "b-home", "label": "Other app", "app": "beta"},
    ]
    ws = {"app": "acme", "home_page": "a-home"}
    assert [d["name"] for d in _dashboards(ws, pages)] == ["a-home", "a-stats"]
    # A home page the user may not open is simply left out.
    assert [d["name"] for d in _dashboards(ws, pages[:1])] == ["a-stats"]
    assert _dashboards({"app": "", "home_page": None}, pages) == []
