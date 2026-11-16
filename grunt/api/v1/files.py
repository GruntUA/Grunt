"""Public files by a path with their extension: ``/api/v1/files/<file id>.<ext>``.

See :func:`grunt.storage.doctypes.File.file.public_file`.
"""

from fastapi import Request, Response

from grunt.api.router import GruntRouter
lazy from grunt.storage.doctypes.File.file import public_file

# Guests (and Office for the web) read published files without a token.
router = GruntRouter(optional_auth=True)


@router.get("/files/{filename}")
async def get_public_file(filename: str, request: Request) -> Response:
    """A public file, inline where the browser can show it."""
    return await public_file(filename, request)
