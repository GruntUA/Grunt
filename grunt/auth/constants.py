"""Identity constants with no dependencies - importable from any layer."""

# The internal identity of `grunt.system_context()` (background tasks, hooks,
# migrations). ``grunt.auth.doctypes.User.user.SYSTEM_USER`` carries it.
SYSTEM_USER_EMAIL = "system@grunt.local"
