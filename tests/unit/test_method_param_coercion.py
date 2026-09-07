"""``_process_params`` coerces numeric/bool query strings — but a parameter
explicitly annotated ``str`` must keep its raw value, so a Link search for a
numeric term ("12345") doesn't arrive as an int."""

from __future__ import annotations

from typing import Any

from grunt.api.v1.method import _process_params


async def _sample(doctype: str, search: str = "", per_page: int = 10, flag: bool = False) -> Any:
    return None


def test_str_annotated_param_keeps_numeric_string():
    args = _process_params(
        {"doctype": "Contact", "search": "12345", "per_page": "20", "flag": "true"},
        _sample,
    )
    assert args["search"] == "12345"
    assert args["per_page"] == 20
    assert args["flag"] is True


def test_without_method_legacy_coercion_still_applies():
    args = _process_params({"search": "12345"})
    assert args["search"] == 12345
