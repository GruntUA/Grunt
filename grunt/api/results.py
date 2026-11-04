"""Common result shapes of whitelisted methods.

Annotate a method with one of these (or its own ``TypedDict``) instead of a
bare ``dict``: `grunt app types` turns it into the TS type `grunt.call`
resolves to, so a client script sees the fields.
"""

from typing import NotRequired, TypedDict


class Queued(TypedDict):
    """A background task was queued (its progress arrives over the WebSocket)."""

    queued: bool


class Outcome(TypedDict):
    """Success flag with the reason on failure - for checks the UI reports itself."""

    success: bool
    error: NotRequired[str]
