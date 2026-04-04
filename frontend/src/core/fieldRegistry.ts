/**
 * Field Properties Registry
 *
 * Each fieldtype declares which property sections appear in PropertiesPanel.
 * Add a new fieldtype by calling registerFieldType(...) — no changes to
 * PropertiesPanel required.
 *
 * Section types:
 *   'core'        — Label, Fieldname (always shown, built into panel)
 *   'flags'       — Boolean toggles (Required, Hidden, etc.)
 *   'display'     — In List View, In Filter, Bold
 *   'text'        — Description, Placeholder, Depends On, Mandatory Depends On
 *   'validation'  — Min, Max, Max Length, Regex, Unique
 *   'default'     — Default value input
 *   'options'     — Textarea for Select options
 *   'link'        — Linked DocType selector
 *   'table'       — Child DocType selector
 *   'number'      — Min Value / Max Value (for Int/Float)
 *   'collapsible' — Collapsible toggle (Section only)
 */

export type PropSection =
  | 'core'
  | 'flags'
  | 'display'
  | 'text'
  | 'validation'
  | 'default'
  | 'options'
  | 'link'
  | 'table'
  | 'number'
  | 'collapsible'

export interface FieldTypeConfig {
  /** Human-readable label shown in PropertiesPanel header */
  label: string
  /** Which property sections to show, in order */
  sections: PropSection[]
}

const registry = new Map<string, FieldTypeConfig>()

export function registerFieldType(fieldtype: string, config: FieldTypeConfig): void {
  registry.set(fieldtype, config)
}

export function getFieldConfig(fieldtype: string): FieldTypeConfig | null {
  return registry.get(fieldtype) ?? null
}

export function getAllFieldTypes(): string[] {
  return [...registry.keys()]
}

// ── Registrations ────────────────────────────────────────────────────────────

const DATA_SECTIONS: PropSection[] = ['core', 'flags', 'display', 'text', 'default']

registerFieldType('Text', {
  label: 'Text',
  sections: [...DATA_SECTIONS, 'validation'],
})

registerFieldType('LongText', {
  label: 'Long Text',
  sections: [...DATA_SECTIONS, 'validation'],
})

registerFieldType('Int', {
  label: 'Integer',
  sections: [...DATA_SECTIONS, 'number', 'validation'],
})

registerFieldType('Float', {
  label: 'Float',
  sections: [...DATA_SECTIONS, 'number', 'validation'],
})

registerFieldType('Check', {
  label: 'Checkbox',
  sections: ['core', 'flags', 'display', 'text', 'default'],
})

registerFieldType('Date', {
  label: 'Date',
  sections: DATA_SECTIONS,
})

registerFieldType('Datetime', {
  label: 'Date & Time',
  sections: DATA_SECTIONS,
})

registerFieldType('Time', {
  label: 'Time',
  sections: DATA_SECTIONS,
})

registerFieldType('Select', {
  label: 'Select',
  sections: [...DATA_SECTIONS, 'options'],
})

registerFieldType('Link', {
  label: 'Link',
  sections: [...DATA_SECTIONS, 'link'],
})

registerFieldType('MultiLink', {
  label: 'Multi Link',
  sections: [...DATA_SECTIONS, 'link'],
})

registerFieldType('Attach', {
  label: 'Attach',
  sections: DATA_SECTIONS,
})

registerFieldType('Image', {
  label: 'Image',
  sections: DATA_SECTIONS,
})

registerFieldType('RichText', {
  label: 'Rich Text',
  sections: DATA_SECTIONS,
})

registerFieldType('JSON', {
  label: 'JSON',
  sections: DATA_SECTIONS,
})

registerFieldType('Code', {
  label: 'Code',
  sections: DATA_SECTIONS,
})

registerFieldType('Color', {
  label: 'Color',
  sections: DATA_SECTIONS,
})

registerFieldType('Signature', {
  label: 'Signature',
  sections: ['core', 'flags', 'display', 'text'],
})

registerFieldType('Geolocation', {
  label: 'Geolocation',
  sections: ['core', 'flags', 'display', 'text'],
})

registerFieldType('Table', {
  label: 'Table',
  sections: ['core', 'flags', 'display', 'text', 'table'],
})

// Layout fields
registerFieldType('Section', {
  label: 'Section',
  sections: ['core', 'collapsible', 'text'],
})

registerFieldType('Column', {
  label: 'Column',
  sections: ['core'],
})

registerFieldType('Tab', {
  label: 'Tab',
  sections: ['core'],
})
