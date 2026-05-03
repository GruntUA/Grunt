"""Grunt exception classes."""


class GruntError(Exception):
    """User-facing error raised via ``grunt.throw()``.

    Caught by DocumentService and returned as an HTTP 422 response.
    """

    def __init__(self, message: str, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title
