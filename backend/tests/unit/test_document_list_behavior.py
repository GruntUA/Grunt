import pytest

from grunt.core.document.base import DocumentList


def test_document_list_behavior():
    data = [{"id": "1"}, {"id": "2"}]
    meta = {"total": 2, "page": 1}

    dl = DocumentList(data, meta=meta)

    # 1. Verify it behaves like a list
    assert len(dl) == 2
    assert dl[0] == {"id": "1"}
    assert list(dl) == data

    # 2. Verify backward compatibility (dict-like access)
    assert dl["data"] == data
    assert dl["meta"] == meta
    assert dl.get("data") == data
    assert dl.get("meta") == meta
    assert dl.get("nonexistent") is None
    assert dl.get("nonexistent", "default") == "default"

    # 3. Verify it still errors on invalid keys
    with pytest.raises(TypeError):
        _ = dl[0.5]

    # 4. Verify to_dict
    assert dl.to_dict() == {"data": data, "meta": meta}


if __name__ == "__main__":
    # Allows running standalone
    test_document_list_behavior()
    print("DocumentList tests passed!")
