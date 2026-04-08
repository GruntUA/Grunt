"""Startup routines — populate system DocType tables and seed core data.

Called once during application lifespan startup.
"""

from grunt.core.startup.doctypes import (
    apply_doctype_overrides,
    load_core_doctypes,
    populate_system_doctypes,
)
from grunt.core.startup.settings import seed_system_settings
from grunt.core.startup.workspaces import seed_app_workspaces, seed_grunt_workspace
from grunt.core.startup.fixtures import _load_app_meta
from grunt.core.startup.workspaces import _auto_seed_workspace

__all__ = [
    "apply_doctype_overrides",
    "load_core_doctypes",
    "populate_system_doctypes",
    "seed_system_settings",
    "seed_grunt_workspace",
    "seed_app_workspaces",
    "_load_app_meta",
    "_auto_seed_workspace",
]
