from grunt.metadata.dynamic_options import (
    get_options,
    get_schemas,
    register_option,
    register_schema,
    resolve_field_options,
)
from grunt.metadata.field import DocField
from grunt.website.block_types import BLOCK_TYPE_SOURCE, get_block_template, register_block_type


def test_register_option_and_get_options():
    source = "test.dynamic_options.demo"
    register_option(source, "alpha")
    register_option(source, "beta")
    register_option(source, "alpha")  # duplicate — must not appear twice
    assert get_options(source) == ["alpha", "beta"]


def test_get_options_unknown_source_returns_empty():
    assert get_options("test.dynamic_options.unknown") == []


def test_resolve_field_options_uses_registry_when_options_source_set():
    source = "test.dynamic_options.resolve"
    register_option(source, "x")
    register_option(source, "y")
    field = DocField(fieldname="demo", fieldtype="Select", options_source=source)
    assert resolve_field_options(field) == "x\ny"


def test_resolve_field_options_falls_back_to_static_options():
    field = DocField(fieldname="demo", fieldtype="Select", options="a\nb")
    assert resolve_field_options(field) == "a\nb"


def test_builtin_block_types_are_registered():
    options = get_options(BLOCK_TYPE_SOURCE)
    for name in ("hero", "rich_text", "image", "cta_banner", "columns", "html_embed", "form_embed"):
        assert name in options
    assert get_block_template("hero") == "blocks/hero.html"


def test_register_block_type_extends_select_options():
    register_block_type("__test_custom_block__", "blocks/__test_custom_block__.html")
    assert "__test_custom_block__" in get_options(BLOCK_TYPE_SOURCE)
    assert get_block_template("__test_custom_block__") == "blocks/__test_custom_block__.html"


def test_register_schema_and_get_schemas():
    source = "test.dynamic_options.schema"
    fields_a = [{"fieldname": "foo", "label": "Foo", "fieldtype": "Text"}]
    fields_b = [{"fieldname": "bar", "label": "Bar", "fieldtype": "Int"}]
    register_schema(source, "a", fields_a)
    register_schema(source, "b", fields_b)
    assert get_schemas(source) == {"a": fields_a, "b": fields_b}


def test_get_schemas_unknown_source_returns_empty():
    assert get_schemas("test.dynamic_options.unknown_schema") == {}


def test_builtin_block_types_have_registered_field_schemas():
    schemas = get_schemas(BLOCK_TYPE_SOURCE)
    assert {f["fieldname"] for f in schemas["hero"]} == {"subtitle", "link_url", "link_label"}
    assert {f["fieldname"] for f in schemas["rich_text"]} == {"body"}
    assert {f["fieldname"] for f in schemas["image"]} == {"image"}
    assert {f["fieldname"] for f in schemas["html_embed"]} == {"embed_html"}
    assert {f["fieldname"] for f in schemas["form_embed"]} == {"form_route"}


def test_register_block_type_with_no_fields_registers_empty_schema():
    register_block_type("__test_custom_block_no_fields__", "blocks/x.html")
    assert get_schemas(BLOCK_TYPE_SOURCE)["__test_custom_block_no_fields__"] == []
