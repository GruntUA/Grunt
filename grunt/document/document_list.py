"""The result of a list read: rows plus pagination meta."""

from typing import Any


class DocumentList[T](list[T]):
    """A list of rows plus pagination meta (``.meta``); ``to_dict()`` gives the
    ``{"data": ..., "meta": ...}`` response shape."""

    def __init__(self, data: list[T], meta: dict[str, Any] | None = None) -> None:
        super().__init__(data)
        self.meta = meta or {}

    def __eq__(self, other: object) -> bool:
        # Equal as a list: ``meta`` is pagination of this read, not content.
        return super().__eq__(other)

    def to_dict(self) -> dict[str, Any]:
        return {"data": list(self), "meta": self.meta}
