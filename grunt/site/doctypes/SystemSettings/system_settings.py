"""Controller for the SystemSettings singleton.

It drops the in-process settings cache whenever an admin saves the form, so the
new values take effect immediately in this worker (other workers pick them up
via the cache TTL - see ``grunt/site/settings.py``), and re-applies the default
language to the i18n service.
"""

from grunt.document.base import Document
from grunt.i18n import translation_service
from grunt.site.settings import clear_settings_cache


class SystemSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    app_name: str | None = None  # App name
    app_logo: str | None = None  # Logo
    language: str | None = None  # Default language
    timezone: str | None = None  # Time zone
    date_format: str | None = None  # Date format
    rounding_method: str | None = None  # Rounding
    allow_user_registration: bool | None = None  # Allow self sign-up
    require_signup_approval: bool | None = None  # Registration needs approval
    default_role: str | None = None  # Default role
    default_role_profile: str | None = None  # Default role profile
    log_retention_days: int | None = None  # Keep logs, days
    perf_monitoring_enabled: bool | None = None  # Record performance stats
    report_timeout: int | None = None  # Report timeout, sec
    personal_storage_quota_mb: int | None = None  # Personal space quota, MB
    allowed_file_types: str | None = None  # Allowed file types
    optimize_images: bool | None = None  # Compress uploaded images
    image_format: str | None = None  # Store images as
    image_max_size: int | None = None  # Max image size, px
    image_quality: int | None = None  # Image quality
    comment_reactions: str | None = None  # Comment reactions
    sidebar_modules_after: int | None = None  # Sidebar: modules from
    count_page_views: bool | None = None  # Count page views
    password_min_length: int | None = None  # Minimum password length
    password_require_uppercase: bool | None = None  # Uppercase letters (A–Z)
    password_require_lowercase: bool | None = None  # Lowercase letters (a–z)
    password_require_numbers: bool | None = None  # Digits (0–9)
    password_require_symbols: bool | None = None  # Special characters
    password_max_age_days: int | None = None  # Password expires after, days
    session_timeout: int | None = None  # Session lifetime, min
    session_login_history: int | None = None  # Sign-ins kept per device
    max_login_attempts: int | None = None  # Max login attempts
    account_lockout_duration: int | None = None  # Lockout duration, min
    max_sessions_per_user: int | None = None  # Sessions per user
    disable_password_login: bool | None = None  # Sign in with SSO only
    captcha_provider: str | None = None  # Provider
    captcha_site_key: str | None = None  # Site key
    captcha_secret_key: str | None = None  # Secret key
    default_email_account: str | None = None  # Default account
    email_footer: str | None = None  # Email signature
    backup_enabled: bool | None = None  # Make backups automatically
    backup_interval_hours: int | None = None  # Every, hours
    backup_keep: int | None = None  # Keep backups
    backup_include_files: bool | None = None  # Include uploaded files
    backup_compression_level: int | None = None  # Compression level
    default_notification_digest: str | None = None  # Default digest
    enable_web_push: bool | None = None  # Enable push notifications
    webpush_vapid_public: str | None = None  # VAPID Public Key
    webpush_vapid_private: str | None = None  # VAPID Private Key

    # end: auto-generated types

    async def after_save(self) -> None:
        clear_settings_cache()

        translation_service.set_default(self.language)
