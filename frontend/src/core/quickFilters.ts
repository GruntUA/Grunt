import type { DocField, QuickFilter } from '@/types'

export const SUPPORTED_FIELD_TYPES = new Set([
  'Text', 'Data', 'LongText',
  'Date', 'Datetime', 'Time',
  'Select', 'Check',
  'Int', 'Float',
  'Link',
])

function inferInputType(field: DocField): QuickFilter['input_type'] {
  switch (field.fieldtype) {
    case 'Date':
    case 'Datetime':
      return 'date'
    case 'Select':
      return 'select'
    case 'Check':
      return 'check'
    case 'Int':
    case 'Float':
      return 'number'
    case 'Link':
      return 'link'
    default:
      return 'text'
  }
}

function inferOperator(field: DocField): string {
  if (field.fieldtype === 'Text' || field.fieldtype === 'Data' || field.fieldtype === 'LongText') {
    return 'ilike'
  }
  return 'eq'
}

export function buildQuickFilterForField(field: DocField): QuickFilter {
  const inputType = inferInputType(field)
  // Free-text inputs benefit from a debounce; discrete pickers apply instantly.
  const debounceMs = inputType === 'text' || inputType === 'number' ? 300 : 0
  return {
    id: `qf_${field.fieldname}`,
    field: field.fieldname,
    operator: inferOperator(field),
    label: field.label || field.fieldname,
    input_type: inputType,
    on_change: { mode: 'local', debounce_ms: debounceMs },
    enabled_in: ['list', 'tree'],
  }
}

export function buildQuickFiltersFromFields(fields: DocField[]): QuickFilter[] {
  return fields
    .filter(f => !!f.in_quick_filter && SUPPORTED_FIELD_TYPES.has(f.fieldtype) && !!f.fieldname)
    .map(buildQuickFilterForField)
}

/** Apply a personal field-selection override on top of the doctype's admin-defined defaults. */
export function applyFieldSelection(
  selectedFieldnames: string[],
  adminDefaults: QuickFilter[],
  fields: DocField[],
): QuickFilter[] {
  const byField = new Map(adminDefaults.map(ff => [ff.field, ff]))
  const fieldByName = new Map(fields.map(f => [f.fieldname, f]))
  return selectedFieldnames
    .map(fieldname => byField.get(fieldname) ?? (fieldByName.has(fieldname) ? buildQuickFilterForField(fieldByName.get(fieldname)!) : null))
    .filter((ff): ff is QuickFilter => ff !== null)
}
