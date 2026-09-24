/**
 * Currency field helpers. `field.options` names the currency: a sibling Link
 * fieldname (Currency is named by its ISO code) or a fixed ISO code like `UAH`.
 */
import type { DocField } from '@/types'
import { localeTag } from './datetime'

export function currencyCode(field: DocField, doc?: Record<string, unknown>): string | null {
  const opt = field.options?.trim()
  if (!opt) return null
  if (doc && opt in doc) return typeof doc[opt] === 'string' && doc[opt] ? (doc[opt] as string) : null
  return /^[A-Z]{3}$/.test(opt) ? opt : null
}

function formatter(code: string | null): Intl.NumberFormat {
  const plain = { minimumFractionDigits: 2, maximumFractionDigits: 2 }
  if (!code) return new Intl.NumberFormat(localeTag(), plain)
  try {
    return new Intl.NumberFormat(localeTag(), { ...plain, style: 'currency', currency: code, currencyDisplay: 'narrowSymbol' })
  } catch {
    return new Intl.NumberFormat(localeTag(), plain) // unknown code
  }
}

/** `12 345,67 ₴` — or `12 345,67` when the currency is unknown. */
export function formatCurrency(value: unknown, code: string | null): string {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  return Number.isFinite(n) ? formatter(code).format(n) : String(value)
}

/** `₴` for UAH; the code itself when Intl has no symbol for it. */
export function currencySymbol(code: string | null): string {
  if (!code) return ''
  return formatter(code).formatToParts(0).find((p) => p.type === 'currency')?.value ?? code
}
