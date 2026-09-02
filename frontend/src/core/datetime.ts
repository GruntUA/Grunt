/**
 * Centralised date/time presentation.
 *
 * Every user-facing date string in the app goes through here so that the
 * `SystemSettings` values `date_format` and `timezone` (plus `language` for
 * month/weekday names) take effect everywhere at once.
 *
 * - `formatDate` / `formatDateTime` are **pattern-driven** — they honour
 *   `date_format` (dd.mm.yyyy | dd/mm/yyyy | yyyy-mm-dd).
 * - `formatDayMonth` / `formatWeekday` / `formatFull` / `formatIntl` are
 *   locale-driven (short human labels, timeline chrome, export headers).
 *
 * Config is read live from `siteConfigState()` so changing SystemSettings and
 * reloading the SPA is enough — no rebuild.
 */

import { siteConfigState } from '@/core/composables/useSiteConfig'

export const EMPTY_DATE = '—'

type DateInput = Date | string | number | null | undefined

function toDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'number') {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? null : d
  }
  // "2026-08-28 09:30:00" → ISO-parseable. Server timestamps are always UTC;
  // a date-time string with no zone designator is parsed by JS as *local*
  // time, so tag a bare one as UTC before `Intl` re-localises it.
  let s = String(value).trim().replace(' ', 'T')
  if (/T\d{2}:\d{2}/.test(s) && !/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? null : d
}

function localeTag(): string {
  return siteConfigState().language || 'uk-UA'
}

function timeZone(): string | undefined {
  return siteConfigState().timezone || undefined
}

function partsOf(d: Date, opts: Intl.DateTimeFormatOptions): Record<string, string> {
  const out: Record<string, string> = {}
  for (const p of new Intl.DateTimeFormat('en-GB', { timeZone: timeZone(), ...opts }).formatToParts(d)) {
    out[p.type] = p.value
  }
  return out
}

export function formatDate(value: DateInput, opts: { time?: boolean } = {}): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE

  const p = partsOf(d, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(opts.time ? { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' } : {}),
  })

  const { year: y, month: m, day } = p
  let datePart: string
  switch (siteConfigState().dateFormat || 'dd.mm.yyyy') {
    case 'yyyy-mm-dd':
      datePart = `${y}-${m}-${day}`
      break
    case 'dd/mm/yyyy':
      datePart = `${day}/${m}/${y}`
      break
    default:
      datePart = `${day}.${m}.${y}`
  }

  if (opts.time) {
    const hh = (p.hour ?? '00').padStart(2, '0')
    const mm = (p.minute ?? '00').padStart(2, '0')
    return `${datePart} ${hh}:${mm}`
  }
  return datePart
}

export function formatDateTime(value: DateInput): string {
  return formatDate(value, { time: true })
}

export function formatTime(value: DateInput): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  const p = partsOf(d, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  return `${(p.hour ?? '00').padStart(2, '0')}:${(p.minute ?? '00').padStart(2, '0')}`
}

/** Short label like "28 серп." — for activity feeds / timelines. */
export function formatDayMonth(value: DateInput): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  return new Intl.DateTimeFormat(localeTag(), {
    timeZone: timeZone(),
    day: 'numeric',
    month: 'short',
  }).format(d)
}

export function formatWeekday(value: DateInput, style: 'long' | 'short' = 'long'): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  return new Intl.DateTimeFormat(localeTag(), { timeZone: timeZone(), weekday: style }).format(d)
}

/** Long, locale-formatted — for export headers and share banners. */
export function formatFull(value: DateInput): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  return new Intl.DateTimeFormat(localeTag(), {
    timeZone: timeZone(),
    dateStyle: 'long',
    timeStyle: 'short',
  }).format(d)
}

export interface DateFormatSpec {
  /** separator between date parts */
  sep: string
  /** order of the three parts */
  order: Array<'d' | 'm' | 'y'>
  /** localized input placeholder, e.g. "ДД.ММ.РРРР" */
  placeholder: string
}

/** How `DatePicker` should render / mask / parse a typed date, per `date_format`. */
export function dateFormatSpec(): DateFormatSpec {
  switch (siteConfigState().dateFormat) {
    case 'yyyy-mm-dd':
      return { sep: '-', order: ['y', 'm', 'd'], placeholder: 'РРРР-ММ-ДД' }
    case 'dd/mm/yyyy':
      return { sep: '/', order: ['d', 'm', 'y'], placeholder: 'ДД/ММ/РРРР' }
    default:
      return { sep: '.', order: ['d', 'm', 'y'], placeholder: 'ДД.ММ.РРРР' }
  }
}

/** Escape hatch: locale + timezone applied, caller supplies the Intl options. */
export function formatIntl(value: DateInput, opts: Intl.DateTimeFormatOptions): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  return new Intl.DateTimeFormat(localeTag(), { timeZone: timeZone(), ...opts }).format(d)
}

const REL_STEPS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

/**
 * Locale-aware "2 дні тому" / "щойно". Pair with `formatFull` in a tooltip
 * for the exact timestamp.
 */
export function formatRelative(value: DateInput): string {
  const d = toDate(value)
  if (!d) return EMPTY_DATE
  const seconds = Math.round((d.getTime() - Date.now()) / 1000)
  const abs = Math.abs(seconds)
  const rtf = new Intl.RelativeTimeFormat(localeTag(), { numeric: 'auto' })
  if (abs < 45) return rtf.format(0, 'second')
  for (const [unit, secs] of REL_STEPS) {
    if (abs >= secs) return rtf.format(Math.round(seconds / secs), unit)
  }
  return rtf.format(0, 'second')
}
