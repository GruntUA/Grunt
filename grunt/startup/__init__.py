"""Startup routines - load core DocTypes and seed core data.

Called once during application lifespan startup.
"""

from grunt.startup.app_install import sync_installed_apps
from grunt.startup.doctypes import (
    apply_doctype_overrides,
    load_core_doctypes,
    sync_all_doctypes,
)
from grunt.startup.fixtures import load_core_fixtures
from grunt.startup.settings import seed_system_settings
from grunt.startup.validators import load_validators
from grunt.startup.workspaces import seed_grunt_workspace

__all__ = [
    "apply_doctype_overrides",
    "load_core_doctypes",
    "sync_all_doctypes",
    "seed_system_settings",
    "seed_grunt_workspace",
    "sync_installed_apps",
    "load_core_fixtures",
    "load_validators",
]
