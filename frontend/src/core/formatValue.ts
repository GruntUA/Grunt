/**
 * Plain-text value formatting - one place for exports, map popups, reports and
 * anything else that shows a field value outside its own Vue component.
 *
 * A field type with a special text form ships components/fields/<Type>/format.ts
 * whose default export is a ValueFormatter (discovered by folder name, like
 * ListCell.vue). Everything else falls back to: numbers in the UI locale,
 * objects as JSON, the rest as a string. Plugin apps can register one too:
 *
 *   import { registerFormatter } from '@/core/formatValue'
 *   registerFormatter('MyType', (value) => `#${value}`)
 *
 * The result is plain text - escape it before putting it into HTML.
 */

import type { DocField } from '@/types'
import { byFieldType, isNumericType } from '@/core/fieldRegistry'
import { formatNumber } from '@/core/currency'

export type FormatField = Pick<DocField, 'fieldtype'> & Partial<Pick<DocField, 'options'>>

/** Formats a non-empty value of a field as plain text. */
export type ValueFormatter = (value: unknown, field: FormatField) => string

/** Shown for an empty value. */
export const EMPTY_VALUE = '—'

const _discovered = byFieldType(
  import.meta.glob<ValueFormatter>('@/components/fields/*/format.ts', { eager: true, import: 'default' }),
)
const _registry = new Map<string, ValueFormatter>()

/** Register or override the formatter for a field type. */
export function registerFormatter(fieldtype: string, formatter: ValueFormatter): void {
  _registry.set(fieldtype, formatter)
}

function fallback(value: unknown, field: FormatField): string {
  if (isNumericType(field.fieldtype)) {
    const n = Number(value)
    if (Number.isFinite(n)) return formatNumber(n)
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** `value` of `field` as plain text, `—` when empty. */
export function formatValue(field: FormatField, value: unknown): string {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE
  const formatter = _registry.get(field.fieldtype) ?? _discovered.get(field.fieldtype) ?? fallback
  return formatter(value, field)
}
