/**
 * Duration field helpers. The stored number is seconds by default;
 * `field.options = "ms"` makes it milliseconds (e.g. Redis idle times).
 */
import i18n, { N_ } from '@/plugins/i18n'
import type { DocField } from '@/types'

export type DurationUnit = 's' | 'ms'

const UNITS: [key: string, ms: number][] = [
  [N_('{n} d'), 86_400_000],
  [N_('{n} h'), 3_600_000],
  [N_('{n} min'), 60_000],
  [N_('{n} s'), 1_000],
]

export function durationUnit(field: Pick<DocField, 'options'>): DurationUnit {
  return field.options?.trim().toLowerCase() === 'ms' ? 'ms' : 's'
}

/**
 * `2 d 3 h 15 min` - `maxParts` consecutive units from the largest non-zero
 * one, the rest dropped (`1 d 0 h 5 min` at 2 parts is `1 d`).
 * Sub-second values of a `ms` field read as `450 ms`. Empty for no value.
 */
export function formatDuration(value: unknown, unit: DurationUnit = 's', maxParts = Infinity): string {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)

  const t = (key: string, v: number) => i18n.global.t(key, { n: String(v) })
  const sign = n < 0 ? '−' : ''
  let rest = Math.round(Math.abs(n) * (unit === 'ms' ? 1 : 1000))
  if (unit === 'ms' && rest < 1000) return sign + t(N_('{n} ms'), rest)

  rest = Math.round(rest / 1000) * 1000 // whole seconds from here on
  const parts: string[] = []
  let slots = 0 // units consumed since the largest non-zero one, zeros included
  for (const [key, size] of UNITS) {
    const count = Math.floor(rest / size)
    rest %= size
    if (!count && !slots) continue
    if (slots++ >= maxParts) break
    if (count) parts.push(t(key, count))
  }
  return sign + (parts.join(' ') || t(N_('{n} s'), 0))
}

export interface DurationSegment {
  key: 'd' | 'h' | 'min' | 's' | 'ms'
  /** i18n key of the unit's caption. */
  label: string
  /** Size of one step in the field's stored unit. */
  size: number
  count: number
}

const SEGMENTS: [key: DurationSegment['key'], label: string, ms: number][] = [
  ['d', N_('Days'), 86_400_000],
  ['h', N_('Hours'), 3_600_000],
  ['min', N_('Minutes'), 60_000],
  ['s', N_('Seconds'), 1_000],
  ['ms', N_('Milliseconds'), 1],
]

/**
 * The editor's segments for a stored total - days absorb everything above a
 * day; a seconds field has no `ms` segment and its fraction is dropped.
 */
export function splitDuration(total: number, unit: DurationUnit = 's'): DurationSegment[] {
  const perUnit = unit === 'ms' ? 1 : 1000
  let rest = Math.max(0, Math.round(total * perUnit))
  return SEGMENTS.filter(([, , ms]) => ms >= perUnit).map(([key, label, ms]) => {
    const count = Math.floor(rest / ms)
    rest %= ms
    return { key, label, size: ms / perUnit, count }
  })
}
