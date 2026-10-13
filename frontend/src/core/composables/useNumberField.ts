/**
 * Shared bits of the number fields built on shadcn's NumberField (Int, Float,
 * Currency, Percent): the UI locale for formatting, the field value from the
 * NumberField, and the decimal key.
 */
import { localeTag } from '@/core/datetime'

export function decimalSeparator(locale: string): string {
  return new Intl.NumberFormat(locale).formatToParts(1.1).find((p) => p.type === 'decimal')?.value ?? '.'
}

/**
 * The period key types the locale's decimal separator. NumberField checks every
 * keystroke against the locale, so where the separator is a comma (uk) "1." is
 * rejected - and the numpad's decimal key sends a period.
 */
export function onDecimalKey(e: KeyboardEvent) {
  if (e.key !== '.' || e.ctrlKey || e.metaKey || e.altKey) return
  const sep = decimalSeparator(localeTag())
  if (sep === '.') return
  e.preventDefault()
  const el = e.target as HTMLInputElement
  const end = el.value.length
  el.setRangeText(sep, el.selectionStart ?? end, el.selectionEnd ?? end, 'end')
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

/** NumberField emits NaN/undefined for an emptied input; the document stores null. */
export function fieldNumber(v: unknown, round: (n: number) => number = (n) => n): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? round(v) : null
}

export { localeTag }
