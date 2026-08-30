/**
 * Cell-level helpers shared by `Table.vue` and `TableEditRow.vue` — display
 * text, per-cell validation, Select options, and subtotal rendering. Kept in
 * one place so the row component computes them itself instead of receiving
 * four freshly-allocated function props on every parent render.
 */
import { toValue, type MaybeRefOrGetter } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DocField } from '@/types'
import { getLayoutTypeSet } from '@/core/fieldRegistry'
import { validateFieldValue } from '@/core/validators'

const LAYOUT_TYPES = getLayoutTypeSet()

/** Backend-injected total rows carry `__is_subtotal` (legacy: `_is_subtotal`). */
export function isSubtotalRow(row: Record<string, unknown>): boolean {
  return !!(row['__is_subtotal'] ?? row['_is_subtotal'])
}

/** Structural rows (Tab / Section / Column…) hold no data — never validate them. */
export function isLayoutRow(row: Record<string, unknown>): boolean {
  return LAYOUT_TYPES.has(String(row['fieldtype'] ?? ''))
}

export function useTableCell(displayedColumns: MaybeRefOrGetter<DocField[]>) {
  const { t } = useI18n()

  function selectOptions(f: DocField): string[] {
    return (f.options ?? '').split('\n').filter(Boolean)
  }

  /**
   * First validation message for a cell, or null. Mirrors the checks the
   * backend would run so the user fixes the row before hitting Save.
   *
   * `includeRequired: false` reports only "wrong" values (bad format / number /
   * validator), not "not filled in yet" — used for the loud row-level summary
   * and the Add-row gate so untouched required cells don't cry wolf.
   */
  function cellError(
    row: Record<string, unknown>,
    f: DocField,
    opts: { includeRequired?: boolean } = {},
  ): string | null {
    if (isSubtotalRow(row) || isLayoutRow(row)) return null

    const v = row[f.fieldname]
    const empty = v === null || v === undefined || v === ''

    if (f.required && empty) return opts.includeRequired === false ? null : t('Required')
    if (empty) return null

    const s = String(v)
    if (f.max_length && s.length > f.max_length) return `${t('Max length')}: ${f.max_length}`
    if (f.regex) {
      try {
        if (!new RegExp(f.regex).test(s)) return t('Invalid format')
      } catch {
        /* bad regex in metadata — ignore */
      }
    }
    if (f.fieldtype === 'Int' || f.fieldtype === 'Float') {
      const n = Number(v)
      if (Number.isNaN(n)) return t('Must be a number')
      if (f.min_value != null && n < f.min_value) return `${t('Min')}: ${f.min_value}`
      if (f.max_value != null && n > f.max_value) return `${t('Max')}: ${f.max_value}`
    }
    if (f.validator) return validateFieldValue(f.validator, v)
    return null
  }

  /** Display value for non-editable cells (complex types or disabled mode). */
  function cellDisplay(row: Record<string, unknown>, f: DocField): string {
    const val = row[f.fieldname]
    if (val === null || val === undefined || val === '') return ''
    if (f.fieldtype === 'Check') return val ? t('Yes') : t('No')
    return f.fieldtype === 'Link' || f.fieldtype === 'Attach'
      ? String(row[`${f.fieldname}__label`] ?? val)
      : String(val)
  }

  /**
   * Subtotal rows are injected by the backend with their own cell values.
   * Render whatever the row carries; if the first column has no value, label
   * it generically — no hardcoded fieldnames.
   */
  function subtotalCellDisplay(row: Record<string, unknown>, f: DocField): string {
    const v = row[f.fieldname]
    if (v !== null && v !== undefined && v !== '') {
      if (f.fieldtype === 'Float' || f.fieldtype === 'Int') {
        const n = Number(v)
        return Number.isNaN(n) ? String(v) : n.toFixed(f.fieldtype === 'Int' ? 0 : 2)
      }
      return String(v)
    }
    return toValue(displayedColumns)[0]?.fieldname === f.fieldname ? `${t('Total')}:` : ''
  }

  return { selectOptions, cellError, cellDisplay, subtotalCellDisplay }
}
