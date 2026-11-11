"""Identity constants with no dependencies - importable from any layer."""

# The internal identity of `system_context()` (background tasks, hooks,
# migrations). ``grunt.auth.doctypes.User.user.SYSTEM_USER`` carries it.
SYSTEM_USER_EMAIL = "system@grunt.local"

# Anonymous visitors of the public site (form submissions, uploads) act as this
# identity - the Guest role's permissions only (``User.user.guest_user()``).
GUEST_USER_EMAIL = "guest@grunt.local"
