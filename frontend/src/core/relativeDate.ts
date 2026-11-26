/**
 * Relative date filter values: `today`, `today-30`, `today+7` (days). The
 * server resolves them when the filter is applied (grunt/utils/dates.py), so a
 * saved filter or a link keeps meaning "the last 30 days" tomorrow too.
 */

const RELATIVE_DATE = /^today(?:\s*([+-])\s*(\d{1,5}))?$/i

/** Days from today a relative value stands for; `null` for any other value. */
export function parseRelativeDays(value: string | null | undefined): number | null {
  const m = RELATIVE_DATE.exec((value ?? '').trim())
  if (!m) return null
  const days = Number(m[2] ?? 0)
  return m[1] === '-' ? -days : days
}

/** The most days a value may hold - five digits, as both parsers read it. */
export const MAX_RELATIVE_DAYS = 99999

/** The filter value for *days* from today: `0` -> `today`, `-30` -> `today-30`
 * (kept within ±{@link MAX_RELATIVE_DAYS}). */
export function relativeDateValue(days: number): string {
  const n = Math.max(-MAX_RELATIVE_DAYS, Math.min(MAX_RELATIVE_DAYS, Math.trunc(days) || 0))
  if (n === 0) return 'today'
  return n < 0 ? `today-${-n}` : `today+${n}`
}
