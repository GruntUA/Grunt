"""``grunt.document.pipeline``: the framework's write extensions are always there,
and a write without the workflow guard is refused, not let through."""

import pytest

from grunt.document import pipeline


def test_core_extensions_load_on_first_use():
    names = {e.name for e in pipeline.extensions()}
    assert {"workflow", "website", "webhooks", "activity", "realtime"} <= names


def test_without_the_workflow_guard_a_write_is_refused(monkeypatch):
    monkeypatch.setattr(pipeline, "_core_loaded", True)
    monkeypatch.setattr(
        pipeline, "_extensions", [e for e in pipeline.extensions() if e.name != "workflow"]
    )
    with pytest.raises(RuntimeError, match="workflow"):
        pipeline.extensions()
