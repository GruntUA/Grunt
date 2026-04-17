import pytest

from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.loader import load_doctype_from_file


def test_load_doctype_from_file():
    # Load "DocType" itself from file
    dt_dict = load_doctype_from_file("DocType")

    assert isinstance(dt_dict, dict)
    assert dt_dict["name"] == "DocType"

    # Check that field classifications are applied
    fields = dt_dict.get("fields", [])
    assert len(fields) > 0
    assert all(f["doctype"] == "DocField" for f in fields)

    # Check that permissions are classified
    perms = dt_dict.get("permissions", [])
    if perms:
        assert all(p["doctype"] == "DocPerm" for p in perms)

    # Ensure it maps properly to Grunt's Pydantic model
    dt_model = DocType.model_validate(dt_dict)
    assert dt_model.name == "DocType"
    assert len(dt_model.fields) == len(fields)


def test_load_doctype_from_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_doctype_from_file("NonExistentDocType123")
