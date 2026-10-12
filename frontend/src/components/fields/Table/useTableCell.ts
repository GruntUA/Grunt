/**
 * Cell helpers for the Table field - which cells are edited inline, what a
 * read-only cell shows, and per-cell validation (mirrors the backend so the
 * user fixes a row before Save).
 */
import i18n from '@/plugins/i18n'
import type { DocField } from '@/types'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { validateFieldValue } from '@/core/validators'
import { currencyCode, formatCurrency } from '@/core/currency'
import { selectOptionLabel } from '@/lib/selectOptions'

const LAYOUT_TYPES = getLayoutTypeSet()

/** Field types edited right in the grid cell; the rest only in the row sheet. */
export const INLINE_TYPES = new Set([
  'Data',
  'Text',
  'Int',
  'Float',
  'Currency',
  'Check',
  'Select',
  'Date',
  'Datetime',
  'Time',
  'Link',
])

/** Structural rows (Tab / Section / Column… in a DocField table) hold no data. */
export function isLayoutRow(row: Record<string, unknown>): boolean {
  return LAYOUT_TYPES.has(String(row['fieldtype'] ?? ''))
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === ''
}

const t = (key: string): string => i18n.global.t(key)

/** VARCHAR length of a Data / Text column - mirrors the server's column_spec. */
function textLimit(f: DocField): number | null {
  if (f.fieldtype !== 'Data' && f.fieldtype !== 'Text') return f.max_length || null
  return Math.max(64, Math.min(f.max_length || 255, 1000))
}

/**
 * First validation message for a cell, or null. `includeRequired: false`
 * reports only wrong values, not "not filled in yet" - for the row summary
 * and the Add-row gate, so untouched required cells don't cry wolf.
 */
export function cellError(
  row: Record<string, unknown>,
  f: DocField,
  opts: { includeRequired?: boolean } = {},
): string | null {
  if (isLayoutRow(row)) return null
  const v = row[f.fieldname]
  if (isEmpty(v)) return f.required && opts.includeRequired !== false ? t('Required') : null

  const s = String(v)
  const limit = textLimit(f)
  if (limit && s.length > limit) return `${t('Max length')}: ${limit}`
  if (f.regex) {
    try {
      if (!new RegExp(f.regex).test(s)) return t('Invalid format')
    } catch {
      /* bad regex in metadata - ignore */
    }
  }
  if (f.fieldtype === 'Int' || f.fieldtype === 'Float' || f.fieldtype === 'Currency') {
    const n = Number(v)
    if (Number.isNaN(n)) return t('Must be a number')
    if (f.min_value != null && n < f.min_value) return `${t('Min')}: ${f.min_value}`
    if (f.max_value != null && n > f.max_value) return `${t('Max')}: ${f.max_value}`
  }
  return f.validator ? validateFieldValue(f.validator, v) : null
}

export function useTableCell() {
  /** Text of a cell that is not edited inline (read-only table, complex type). */
  function cellDisplay(row: Record<string, unknown>, f: DocField): string {
    const v = row[f.fieldname]
    if (isEmpty(v)) return ''
    if (f.fieldtype === 'Check') return v ? t('Yes') : t('No')
    if (f.fieldtype === 'Currency') return formatCurrency(v, currencyCode(f, row))
    if (f.fieldtype === 'Select') return selectOptionLabel(f, v)
    const label = row[`${f.fieldname}__label`]
    if (!isEmpty(label)) return String(label)
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }

  return { cellError, cellDisplay }
}
