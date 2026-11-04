/** Field metadata and the runtime field-component contract. */

/**
 * Field type identifier. Fully open - the real set is resolved at runtime by
 * the field registry (src/core/fieldRegistry.ts), which discovers core types
 * from the manifest.json files under components/fields/ and lets any plugin
 * app add its own via registerField().
 */
export type FieldType = string

/** Standard props contract for runtime field components */
export interface BaseFieldProps {
  field: DocField
  modelValue: unknown
  disabled?: boolean
  error?: string
  doc?: Record<string, unknown>
}

export interface IndexHint {
  field: string
  reason: string
}

export interface DocField {
  fieldname: string
  label: string
  fieldtype: FieldType
  // Validation
  required?: boolean
  unique?: boolean
  index?: boolean
  read_only?: boolean
  hidden?: boolean
  bold?: boolean
  // Display
  in_list_view?: boolean
  in_filter?: boolean
  in_quick_filter?: boolean
  /** Date/Datetime quick filter: 'year' - pick a calendar year (`field__year`) instead of a date. */
  quick_filter_mode?: 'year' | null
  /** Editable inline in the Report (spreadsheet) grid view. */
  editable_in_grid?: boolean
  // Type-specific
  options?: string
  /** Select / MultiSelect - captions go through the translation catalog. */
  translatable?: boolean
  /** Served for `translatable` fields: {stored value: caption in the user's language}. */
  option_labels?: Record<string, string>
  // Name of a backend registry source whose values replace `options` - see
  // grunt.metadata.dynamic_options. Already resolved into `options` by the
  // time the schema reaches the frontend; kept here for completeness.
  options_source?: string | null
  // Name of a backend schema registry source (grunt.metadata.dynamic_options)
  // whose {key: fields} variants are resolved into `dynamic_schemas` at
  // schema-serve time. `dynamic_schema_key` names the sibling field in the
  // same row whose value selects which variant applies.
  dynamic_schema_source?: string | null
  dynamic_schema_key?: string | null
  dynamic_schemas?: Record<string, DocField[]>
  default?: unknown
  description?: string
  placeholder?: string
  // Validation rules
  min_value?: number
  max_value?: number
  max_length?: number
  regex?: string
  // Conditional
  depends_on?: string
  mandatory_depends_on?: string
  formula?: string | null
  // Aggregation
  aggregate_function?: string | null
  aggregate_table?: string | null
  aggregate_field?: string | null
  // Link
  link_filters?: string | null
  // Quick Entry
  in_quick_entry?: boolean
  /** Shown in the link hover card (DocType.show_preview_popup). */
  in_preview?: boolean
  // Layout
  columns?: number
  collapsible?: boolean
  /** Tab fields only - render the "Зв'язки" (connections) panel inside this tab. */
  show_connections?: boolean
  icon?: string
  /** Tab fields only - mount a bespoke component as the tab body (e.g. "DesignerTab"). */
  tab_component?: string
  /** App whose `doctype_ext/` added this field to another app's DocType. */
  source_app?: string | null
  /** Values of this field that other apps' properties replaced: app -> {attribute: own value}. */
  ext_base?: Record<string, Record<string, unknown>> | null
  insert_after?: string | null
  // Virtual
  is_virtual?: boolean
  read_formula?: string | null
  // Fetch From
  fetch_from?: string | null
  // Named validator (e.g. "email", "phone", "url", "iban_ua")
  validator?: string | null
  // Password field - show a live checklist of the SystemSettings password policy.
  show_strength?: boolean
  // Table field - group rows by this child fieldname
  group_by?: string | null
}
