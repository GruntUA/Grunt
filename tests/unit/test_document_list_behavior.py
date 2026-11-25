from grunt.document.document_list import DocumentList


def test_document_list_behavior():
    data = [{"name": "1"}, {"name": "2"}]
    meta = {"total": 2, "page": 1}

    dl = DocumentList(data, meta=meta)

    # A list - with the pagination of the read in .meta
    assert len(dl) == 2
    assert dl[0] == {"name": "1"}
    assert list(dl) == data
    assert dl == data
    assert dl.meta == meta

    # The {"data", "meta"} response shape
    assert dl.to_dict() == {"data": data, "meta": meta}
