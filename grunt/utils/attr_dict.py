"""``AttrDict`` - a dict whose keys are also accessible as attributes.

``d.key`` reads ``d["key"]``; a missing key raises ``AttributeError`` (like
``d["key"]`` raises ``KeyError``), so a typo or a field not asked for in
``fields=[...]`` fails where it is read - and in Jinja ``d.key is defined`` /
``d.key | default(...)`` work as for a plain dict. ``d.get("key")`` is there for
a key that may be absent. ``d.key = 1`` sets ``d["key"]``. It is still a
``dict``: ``d["key"]``, ``**d`` and JSON work as before.

The documents and rows that ``grunt.get_doc`` / ``new_doc`` / ``save_doc`` /
``get_list`` and ``grunt.db.get_all`` / ``get_doc`` / ``get_value(as_dict=True)``
return are ``AttrDict`` - child-table rows too::

    todo = await grunt.new_doc("ToDo", {"description": "Call"})
    todo.status            # == todo["status"]

A field named like a ``dict`` method (``items``, ``values``, ``keys``, ``get``,
``update``, ``copy``, ``pop``, ...) reads as that method - use ``d["items"]``.
"""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self

# `dict[str, Any]` for the type checker; a plain `dict` base at run time, so
# static analysers (CodeQL) still see a container class.
if TYPE_CHECKING:
    _Base = dict[str, Any]
else:
    _Base = dict


class AttrDict(_Base):
    """A ``dict`` with attribute-style access (``d.subject`` == ``d["subject"]``)."""

    __slots__ = ()

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key) from None

    def copy(self) -> AttrDict:
        return AttrDict(self)


def as_row(value: Mapping[str, Any]) -> AttrDict:
    """*value* as an :class:`AttrDict` - itself when it already is one, child rows included.

    A list of dicts under a key (child-table rows) gets its dicts converted in
    place, so ``doc["lines"][0].qty`` works too.
    """
    row = value if type(value) is AttrDict else AttrDict(value)
    for v in row.values():
        if type(v) is list:
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    v[i] = as_row(item)  # an AttrDict child is kept, its own children normalised
    return row


def as_rows[L: list[Any]](rows: L) -> L:
    """Each dict of *rows* as an :class:`AttrDict`, in place; returns *rows*."""
    for i, item in enumerate(rows):
        if isinstance(item, dict):
            rows[i] = as_row(item)
    return rows


class DocumentClass(Protocol):
    """What the read API needs of a controller class
    (:class:`grunt.document.base.Document`) - here, so the layers below the
    document one can take a class without importing it::

        rows = await grunt.db.get_all(Invoice, fields=["name", "total"])  # list[Invoice]
    """

    __doctype__: ClassVar[str]

    @classmethod
    def _from_rows(
        cls,
        rows: Iterable[dict[str, Any]],
        *,
        doctype: str | None = None,
        partial: bool = False,
        hidden: frozenset[str] = frozenset(),
    ) -> list[Self]:
        """The rows as documents of the class (``Document._from_rows``)."""
        raise NotImplementedError
