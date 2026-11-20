"""OAuthToken - what a ConnectedApp granted to one document.

Written by :mod:`grunt.integrations.oauth` (connect, refresh); people only
look at it or delete it - deleting disconnects the document.
"""

from datetime import datetime

from grunt.document.base import Document


class OAuthToken(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    connected_app: str  # Connected app
    account: str | None  # Account
    reference_doctype: str  # Document type
    reference_name: str  # Document
    connected_at: datetime | None  # Connected at
    expires_at: datetime | None  # Access expires at
    scopes: str | None  # Scopes
    last_error: str | None  # Last error
    access_token: str | None  # Access token
    refresh_token: str | None  # Refresh token

    # end: auto-generated types
