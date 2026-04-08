import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path("apps/grunt/backend").resolve()))

from grunt.core.metadata.doctype import DocType
from grunt.core.metadata.registry import DocTypeRegistry

registry = DocTypeRegistry()
appeal_json = Path("apps/grunt/backend/grunt/modules/crm/appeal.json").read_text()
doctype_data = json.loads(appeal_json)

# Simulate frontend adding calendar_view
doctype_data["calendar_view"] = {
    "field": "received_date",
    "title_field": "name",
    "sources": []
}

try:
    DocType(**doctype_data)
    print("VALIDATION SUCCESS")
except Exception:
    print("VALIDATION ERROR:")
    import traceback
    traceback.print_exc()
