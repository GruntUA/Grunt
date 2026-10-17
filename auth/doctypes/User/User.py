"""Controller for User.

Lifecycle hooks — override any method to add custom logic:
  before_insert  — before a NEW document is saved to DB
  after_insert   — after a NEW document is saved to DB
  validate       — runs before every save (insert or update), raise to block
  before_save    — before an EXISTING document is updated
  after_save     — after an EXISTING document is updated
  before_delete  — before document is deleted
  after_delete   — after document is deleted

Access fields:
  self.field_name          — read field value
  self.field_name = value  — set field value
  self.data                — full document dict
  self.doctype             — DocType name ("User")
  self.user                — current User (or None)
  self.session             — async SQLAlchemy session (for advanced queries)
"""

from datetime import date, datetime
from typing import Any

from grunt.document.base import Document


class User(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    last_name: str | None  # Last name
    first_name: str | None  # First name
    middle_name: str | None  # Patronymic
    full_name: str | None  # Full name
    avatar: str | None  # Profile photo
    email: str | None  # Email
    phone: str | None  # Phone
    birth_date: date | None  # Date of birth
    gender: str | None  # Gender
    timezone: str | None  # Time zone
    last_login: datetime | None  # Last login
    bio: str | None  # Short bio
    is_active: bool | None  # Active
    signup_state: str | None  # Registration state
    password: str | None  # Set password
    hashed_password: str | None  # Password hash
    storage_quota_mb: int | None  # Personal space quota, MB
    mfa_enabled: bool | None  # MFA enabled
    mfa_setup_button: None  # MFA management
    mfa_secret: str | None  # MFA secret
    mfa_backup_codes: dict | None  # Backup code hashes
    mfa_backup_display: Any | None  # Backup codes
    login_attempts: int | None  # Failed login attempts
    locked_until: datetime | None  # Account locked until
    passkeys_button: None  # Manage passkeys
    theme: str | None  # Theme
    language: str | None  # Language
    reset_token: str | None  # Password reset token
    reset_token_expires_at: datetime | None  # Reset token expiry
    roles: list[dict]  # Table: UserRole

    # end: auto-generated types

    async def validate(self) -> None:
        """Runs before every save — raise an exception to block."""
        pass

    async def before_save(self) -> None:
        """Runs before an existing document is updated."""
        pass

    async def after_save(self) -> None:
        """Runs after document is saved to the database."""
        pass
