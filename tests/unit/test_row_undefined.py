"""grunt.utils.undefined.RowUndefined - a missing key of a row in a template."""

import pytest
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

from grunt.utils.attr_dict import AttrDict
from grunt.utils.undefined import RowUndefined

env = SandboxedEnvironment(undefined=RowUndefined, autoescape=True)


def test_a_missing_key_is_undefined_and_chains():
    tpl = env.from_string(
        "{{ r.a }}|{{ r.b }}|{{ r.b.c }}|{{ r.b is defined }}|{{ r.b | default('-') }}"
    )
    assert tpl.render(r=AttrDict(a=1)) == "1|||False|-"


def test_the_sandbox_still_raises():
    with pytest.raises(SecurityError):
        env.from_string("{{ doc.__class__.__init__.__globals__ }}").render()
