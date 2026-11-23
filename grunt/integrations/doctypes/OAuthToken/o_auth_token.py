"""OAuthToken - what a ConnectedApp granted to one document.

Written by :mod:`grunt.integrations.oauth` (connect, refresh); people only
look at it or delete it - deleting disconnects the document.
"""

from datetime import datetime

from grunt.document.base import Document


class OAuthToken(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    connected_app: str | None = None  # Connected app
    account: str | None = None  # Account
    reference_doctype: str | None = None  # Document type
    reference_name: str | None = None  # Document
    connected_at: datetime | None = None  # Connected at
    expires_at: datetime | None = None  # Access expires at
    scopes: str | None = None  # Scopes
    last_error: str | None = None  # Last error
    access_token: str | None = None  # Access token
    refresh_token: str | None = None  # Refresh token

    # end: auto-generated types
