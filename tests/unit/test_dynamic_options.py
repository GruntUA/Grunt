from grunt.metadata.dynamic_options import (
    get_options,
    get_schemas,
    register_option,
    register_schema,
    resolve_field_options,
)
from grunt.metadata.field import DocField


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


def test_register_schema_and_get_schemas():
    source = "test.dynamic_options.schema"
    fields_a = [{"fieldname": "foo", "label": "Foo", "fieldtype": "Data"}]
    fields_b = [{"fieldname": "bar", "label": "Bar", "fieldtype": "Int"}]
    register_schema(source, "a", fields_a)
    register_schema(source, "b", fields_b)
    assert get_schemas(source) == {"a": fields_a, "b": fields_b}


def test_get_schemas_unknown_source_returns_empty():
    assert get_schemas("test.dynamic_options.unknown_schema") == {}
