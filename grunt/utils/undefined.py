"""``RowUndefined`` - what a Jinja template gets for a key a row doesn't have."""

from typing import Any

from jinja2 import ChainableUndefined, UndefinedError


class RowUndefined(ChainableUndefined):
    """Undefined that chains: ``{{ row.missing.title }}`` renders empty, as it did
    while rows read a missing key as None, and ``row.missing is defined`` /
    ``row.missing | default(...)`` work. What the sandbox refuses
    (``x.__class__.__init__...``) still raises ``SecurityError``."""

    __slots__ = ()

    def __getattr__(self, _name: str) -> Any:
        if self._undefined_exception is not UndefinedError:
            return self._fail_with_undefined_error()
        return self

    def __getitem__(self, _name: str) -> Any:
        return self.__getattr__(_name)
