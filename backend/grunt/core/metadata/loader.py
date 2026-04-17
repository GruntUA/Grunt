import json
from typing import Any

from grunt.core.startup.doctypes import _CORE_DOCTYPES_DIR
from grunt.utils.strings import to_snake_case


def load_doctype_from_file(doctype: str) -> dict[str, Any]:
    """Load DocType definition from its physical JSON file.

    It reads the `.json` file from the core directory, sets the
    `doctype` field on child elements, and returns the raw dictionary.

    Args:
        doctype: Name of the DocType to load

    Returns:
        dict: The loaded DocType configuration.

    Raises:
        FileNotFoundError: If the corresponding .json file cannot be found.
    """
    fname = to_snake_case(doctype)

    file_path = _CORE_DOCTYPES_DIR / fname / f"{fname}.json"

    if not file_path.exists():
        found = list(_CORE_DOCTYPES_DIR.glob(f"**/{fname}.json"))
        if not found:
            raise FileNotFoundError(f"File {fname}.json not found for DocType {doctype}")
        file_path = found[0]

    with open(file_path, encoding="utf-8") as f:
        txt = json.loads(f.read())

    # Add doctype classification for fields and permissions, like Frappe
    for d in txt.get("fields", []):
        d["doctype"] = "DocField"

    for d in txt.get("permissions", []):
        d["doctype"] = "DocPerm"

    # In Frappe they map to BaseDocument here, but raw dicts map better
    # to Grunt's Pydantic workflow when used directly.
    return txt
