"""A DocType as the desk sees it - the JSON the form, list and report builders read."""

from typing import Any

from grunt.i18n import _
from grunt.metadata.doctype import DocType
from grunt.metadata.dynamic_options import get_option_labels, get_schemas, resolve_field_options
from grunt.workflow.registry import get_active_workflow
lazy from grunt.i18n.meta import translate_doctype_meta


async def dump_doctype(dt: DocType, *, translate: bool = False) -> dict[str, Any]:
    """Serialize a DocType, resolving registry-backed options and field schemas.

    Fields with `options_source` set draw their choices from the dynamic
    options registry instead of the static `options` string. Fields with
    `dynamic_schema_source` set get every registered {key: fields} variant
    attached as `dynamic_schemas`, so the frontend can render the variant
    matching a sibling field's value (e.g. WebPageBlock.settings picking its
    form based on block_type) without a second round-trip.

    `workflow_state_field` is resolved from the active `Workflow` document (if
    any) rather than stored on the DocType itself - see grunt/workflow/registry.py.

    ``translate=True`` runs labels/descriptions/Select options through the i18n
    layer for the current request language (see grunt.i18n.meta). Only the
    presentational render paths pass it - never file export / sync.

    The ``actions`` bindings are left as stored: the meta API enriches them
    (grunt/api/v1/meta.py), reports only read the fields.
    """
    data = dt.model_dump()
    for field, fdata in zip(dt.fields, data["fields"], strict=True):
        if field.options_source:
            fdata["options"] = resolve_field_options(field)
            if labels := get_option_labels(field.options_source):
                fdata["option_labels"] = labels
        if field.dynamic_schema_source:
            fdata["dynamic_schemas"] = {
                key: [dict(sub) for sub in fields]
                for key, fields in get_schemas(field.dynamic_schema_source).items()
            }
    workflow = await get_active_workflow(dt.name)
    data["workflow_state_field"] = workflow.state_field if workflow else None
    if workflow and translate:
        # The form hides the state (shown in the sidebar) - it moves by the header's workflow
        # actions (grunt/workflow/guard.py); the builder (raw) keeps the source.
        for fdata in data["fields"]:
            if fdata.get("fieldname") == workflow.state_field:
                fdata["read_only"] = True

    if translate:
        translate_doctype_meta(data)
        for fdata in data["fields"]:
            for variant in (fdata.get("dynamic_schemas") or {}).values():
                for sub in variant:
                    if sub.get("label"):
                        sub["label"] = _(sub["label"])

    return data
