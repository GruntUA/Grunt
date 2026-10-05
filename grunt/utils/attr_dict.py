"""``AttrDict`` - a dict whose keys are also accessible as attributes.

``d.key`` is equivalent to ``d.get("key")`` and returns ``None`` for missing
keys (so optional fields read cleanly). Used as
the ``as_dict`` return type of :meth:`grunt.db.api.GruntDB.get_value`.
"""

from __future__ import annotations

from typing import Any


class AttrDict(dict):
    """A ``dict`` with attribute-style access (``d.subject`` == ``d["subject"]``)."""

    def __getattr__(self, key: str) -> Any:
        # Let dunder lookups (copy, pickle, etc.) fail normally instead of
        # returning None, which would break those protocols.
        if key.startswith("__") and key.endswith("__"):
            raise AttributeError(key)
        return self.get(key)

    __setattr__ = dict.__setitem__  # type: ignore[assignment]
    __delattr__ = dict.__delitem__  # type: ignore[assignment]

    def copy(self) -> AttrDict:
        return AttrDict(self)
