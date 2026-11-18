"""``_`` in templates: translated, then filled from keyword arguments."""

from jinja2 import Environment

from grunt.i18n import use_language
from grunt.i18n.jinja import install


def _render(source: str, **ctx) -> str:
    with use_language("en"):
        return install(Environment(autoescape=True)).from_string(source).render(**ctx)


def test_keyword_params_fill_the_string():
    assert _render('{{ _("Hello, %(name)s,", name=who) }}', who="Ann") == "Hello, Ann,"


def test_params_are_escaped_and_a_bare_percent_stays():
    assert _render('{{ _("Hi %(name)s", name=who) }}', who="<b>") == "Hi &lt;b&gt;"
    assert _render('{{ _("50%") }}') == "50%"


def test_the_percent_form_still_works():
    assert _render('{{ _("%(n)s records") % {"n": 3} }}') == "3 records"
