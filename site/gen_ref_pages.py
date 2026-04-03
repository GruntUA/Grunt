"""Auto-generate Python API reference pages from source modules.

Executed by mkdocs-gen-files during `mkdocs build` or `mkdocs serve`.
For each discovered module it creates a virtual Markdown page containing
a single mkdocstrings `:::` directive, then writes a SUMMARY.md consumed
by mkdocs-literate-nav to build the sidebar navigation automatically.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import mkdocs_gen_files

# Root of the Python package relative to mkdocs.yml
SRC_ROOT = Path("backend")
PKG_ROOT = SRC_ROOT / "grunt"

# Directories to skip entirely
SKIP_DIRS = {
    "__pycache__",
    "alembic",
    "migrations",
    "doctypes",   # app-specific controllers, not public library API
    "apps",       # installed apps scaffold
    "cli",        # Click-based CLI, not importable API
}

# Individual file stems to skip
SKIP_STEMS = {
    "__init__",   # bare re-export shims
    "publish",    # internal deployment helper
    # modules whose optional deps are absent in the docs build environment
    "broker",     # requires taskiq_redis (optional Redis dep)
    "scheduler",  # requires apscheduler + Redis broker
}

# Human-readable section labels for sub-packages (most-specific key wins)
SECTION_LABELS: dict[str, str] = {
    "core/auth": "Auth",
    "core/cache": "Cache",
    "core/data_import": "Data Import",
    "core/db": "Database",
    "core/document": "Document",
    "core/email": "Email",
    "core/hooks": "Hooks",
    "core/i18n": "Internationalisation",
    "core/metadata": "Metadata",
    "core/middleware": "Middleware",
    "core/monitoring": "Monitoring",
    "core/naming": "Naming",
    "core/notification": "Notifications",
    "core/permissions": "Permissions",
    "core/print": "Print",
    "core/reports": "Reports",
    "core/scripting": "Scripting",
    "core/site": "Multi-site",
    "core/storage": "Storage",
    "core/tasks": "Background Tasks",
    "core/utils": "Utilities",
    "core/webform": "Web Forms",
    "core/workflow": "Workflow",
    "api/v1/schemas": "REST Schemas",
    "api/v1": "REST Endpoints",
}


def _module_path(py_file: Path) -> str:
    """Convert a filesystem path to a dotted module path."""
    return ".".join(py_file.relative_to(SRC_ROOT).with_suffix("").parts)


def _should_skip(py_file: Path) -> bool:
    """Return True if this file should be excluded from the reference."""
    for part in py_file.parts:
        if part in SKIP_DIRS:
            return True
    if py_file.stem in SKIP_STEMS or py_file.stem.startswith("test_"):
        return True
    return False


def _section_for(rel: Path) -> str:
    """Return the human-readable section label for a path relative to PKG_ROOT."""
    for n in range(len(rel.parts), 0, -1):
        key = "/".join(rel.parts[:n])
        if key in SECTION_LABELS:
            return SECTION_LABELS[key]
    return rel.parts[0].replace("_", " ").title() if rel.parts else "Misc"


# ── Collect pages ──────────────────────────────────────────────────────────

# Each entry: (page_path_relative_to_api_reference, module_dotted, section)
pages: list[tuple[Path, str, str]] = []

for py_file in sorted(PKG_ROOT.rglob("*.py")):
    if _should_skip(py_file):
        continue

    module = _module_path(py_file)
    rel_to_pkg = py_file.relative_to(PKG_ROOT)       # e.g. core/document/service.py
    page_path = rel_to_pkg.with_suffix(".md")          # e.g. core/document/service.md
    section = _section_for(rel_to_pkg)
    pages.append((page_path, module, section))

# ── Write virtual pages ───────────────────────────────────────────────────

for page_path, module, _ in pages:
    # Full path as seen from the docs root: api/reference/<page_path>
    full_doc_path = Path("api", "reference", page_path)

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        title = module.split(".")[-1].replace("_", " ").title()
        fd.write(f"# {title}\n\n")
        fd.write(f"::: {module}\n")

    mkdocs_gen_files.set_edit_path(full_doc_path, py_file)

# ── Write SUMMARY.md for literate-nav ────────────────────────────────────
# SUMMARY.md lives at api/reference/SUMMARY.md, so paths must be relative
# to that directory — i.e. just <page_path> (no api/reference/ prefix).

sections: dict[str, list[tuple[Path, str]]] = defaultdict(list)
for page_path, module, section in pages:
    sections[section].append((page_path, module))

with mkdocs_gen_files.open("api/reference/SUMMARY.md", "w") as nav:
    for section in sorted(sections):
        nav.write(f"* {section}\n")
        for page_path, module in sorted(sections[section]):
            page_title = module.split(".")[-1].replace("_", " ").title()
            nav.write(f"    * [{page_title}]({page_path})\n")
