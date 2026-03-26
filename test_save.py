import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path("apps/grunt/backend").resolve()))

from grunt.core.metadata.registry import DocTypeRegistry
from grunt.core.metadata.doctype import DocType

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
    doc = DocType(**doctype_data)
    print("VALIDATION SUCCESS")
except Exception as e:
    print("VALIDATION ERROR:")
    import traceback
    traceback.print_exc()
