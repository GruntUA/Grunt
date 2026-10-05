import type { DocType, DocTypeStatusConfig } from '@/types'

const NEUTRAL = 'border-muted-foreground/20 bg-muted/40 text-muted-foreground'
const GREEN = 'border-green-500/30 bg-green-500/10 text-green-700 dark:text-emerald-400'
const BLUE = 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400'
const AMBER = 'border-yellow-500/30 bg-yellow-500/10 text-yellow-700 dark:text-amber-400'
const RED = 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400'

// Single source of truth for status-indicator colours. Every status badge
// (list cells, workflow bar, doc sidebar, form header, mobile cards) renders
// as `<Badge variant="outline" :class="statusToneClass(color)">` - soft tint,
// same look everywhere.
const TONE_CLASSES: Record<string, string> = {
  default: NEUTRAL,
  secondary: NEUTRAL,
  success: GREEN,
  info: BLUE,
  warn: AMBER,
  danger: RED,
  contrast: 'border-foreground/20 bg-foreground text-background',
  // Legacy colour names.
  gray: NEUTRAL,
  blue: BLUE,
  green: GREEN,
  yellow: AMBER,
  orange: AMBER,
  red: RED,
  purple: 'border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300',
  pink: 'border-pink-500/30 bg-pink-500/10 text-pink-700 dark:text-pink-300',
}

/** Tint classes for an indicator colour; unknown/empty -> neutral. */
export function statusToneClass(color: string | null | undefined): string {
  return TONE_CLASSES[color ?? ''] ?? NEUTRAL
}

export interface StatusBadge {
  label: string
  class: string
  icon: string | null
}

/**
 * Bundle a DocType's `status_field` + `status_indicators` into the shape list
 * cells and exporters expect. Returns null when the DocType declares no status
 * field.
 */
export function statusConfigOf(
  dt: DocType | null | undefined,
): DocTypeStatusConfig | null {
  if (!dt?.status_field) return null
  return { field: dt.status_field, indicators: dt.status_indicators ?? [] }
}

/**
 * Resolve the badge for `value` against a DocType's `status_indicators`.
 * Values without an indicator get the neutral tint.
 */
export function statusBadgeFor(
  dt: DocType | null | undefined,
  value: unknown,
): StatusBadge | null {
  if (value == null || value === '') return null
  const val = String(value)
  const ind = dt?.status_indicators?.find((i) => i.value === val)
  return {
    label: ind?.label || val,
    class: statusToneClass(ind?.color),
    icon: ind?.icon ?? null,
  }
}

/**
 * Resolve a document's status badge from its DocType `status_field` (falls
 * back to a bare `status` field). Returns null when there is nothing to show.
 */
export function resolveStatusBadge(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
): StatusBadge | null {
  if (!doc) return null
  return statusBadgeFor(dt, doc[dt?.status_field || 'status'])
}
