import type { BadgeVariants } from '@/components/ui/badge'
import type { DocType, DocTypeStatusConfig } from '@/types'

const STATUS_VARIANT: Record<string, BadgeVariants['variant']> = {
  success: 'success',
  green: 'success',
  info: 'info',
  blue: 'info',
  warn: 'warning',
  yellow: 'warning',
  orange: 'warning',
  danger: 'destructive',
  red: 'destructive',
  secondary: 'secondary',
  gray: 'secondary',
}

export interface StatusBadge {
  label: string
  variant: BadgeVariants['variant']
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
 * Resolve a document's status badge from its DocType `status_field` +
 * `status_indicators`. Falls back to a bare `status` field value with no
 * colour. Returns null when there is nothing to show.
 */
export function resolveStatusBadge(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
): StatusBadge | null {
  if (!doc) return null
  const field = dt?.status_field || 'status'
  const val = doc[field]
  if (val == null || val === '') return null
  const ind = dt?.status_indicators?.find((i) => i.value === String(val))
  return {
    label: ind?.label || String(val),
    variant: (ind && STATUS_VARIANT[ind.color]) || 'secondary',
  }
}
