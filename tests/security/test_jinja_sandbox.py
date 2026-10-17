"""Security regression: the Jinja environments that render DB-stored or
raw-string templates (PrintFormat, grunt.render_template) are sandboxed, so a
template cannot traverse ``__class__``/``__globals__`` into arbitrary code.

These sinks are authored by a System Manager today and not reachable with user
input, but a plain Environment would make them instant SSTI->RCE the moment a
caller forwards untrusted text; the sandbox removes that whole class of risk.
"""

import pytest

ESCAPE = "{{ doc.__class__.__init__.__globals__ }}"


def test_print_render_from_string_blocks_attribute_escape():
    from jinja2.exceptions import SecurityError

    from grunt.print.renderer import render_from_string

    with pytest.raises(SecurityError):
        render_from_string(ESCAPE, {"x": 1})


def test_print_renderer_uses_sandboxed_env():
    from jinja2.sandbox import SandboxedEnvironment

    from grunt.print.renderer import _get_jinja_env

    assert isinstance(_get_jinja_env(), SandboxedEnvironment)


@pytest.mark.asyncio
async def test_render_template_string_is_sandboxed(ctx):
    from jinja2.exceptions import SecurityError

    import grunt

    with pytest.raises(SecurityError):
        await grunt.render_template("{{ now.__class__.__init__.__globals__ }}", {})
