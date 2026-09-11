from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from grunt.startup.doctypes import _find_doctype_dirs

if TYPE_CHECKING:
    from pathlib import Path


def load_doctype_from_file(doctype: str) -> dict[str, Any]:
    """Load DocType definition from its physical JSON file.

    Searches all grunt/*/doctypes/ directories for a matching JSON file.

    Args:
        doctype: Name of the DocType to load (PascalCase)

    Returns:
        dict: The loaded DocType configuration.

    Raises:
        FileNotFoundError: If the corresponding .json file cannot be found.
    """
    # Search in grunt/*/doctypes/{doctype}/{doctype}.json (PascalCase)
    file_path: Path | None = None
    for dt_dir in _find_doctype_dirs():
        candidate = dt_dir / doctype / f"{doctype}.json"
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        # Fallback: glob search across all doctypes directories
        for dt_dir in _find_doctype_dirs():
            found = list(dt_dir.glob(f"**/{doctype}.json"))
            if found:
                file_path = found[0]
                break

    if file_path is None:
        raise FileNotFoundError(f"{doctype}.json not found for DocType {doctype}")

    with open(file_path, encoding="utf-8") as f:
        txt = json.loads(f.read())

    # Add doctype classification for fields and permissions
    for d in txt.get("fields", []):
        d["doctype"] = "DocField"

    for d in txt.get("permissions", []):
        d["doctype"] = "DocPerm"

    # Kept as raw dicts rather than mapped to a model class here — that maps
    # better to Grunt's Pydantic workflow when used directly.
    return txt
