"""The result of a list read: rows plus pagination meta."""

from typing import Any


class DocumentList(list):
    """A list of rows plus pagination meta.

    Iterates and indexes like a list, but ``result["data"]`` and
    ``result["meta"]`` also work, so it can be returned where the
    ``{"data": ..., "meta": ...}`` response shape is expected.
    """

    def __init__(self, data: list, meta: dict[str, Any] | None = None) -> None:
        super().__init__(data)
        self.meta = meta or {}

    def to_dict(self) -> dict[str, Any]:
        return {"data": list(self), "meta": self.meta}

    def __getitem__(self, key: Any) -> Any:
        if key == "data":
            return list(self)
        if key == "meta":
            return self.meta
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key == "data":
            return list(self)
        if key == "meta":
            return self.meta
        return default
