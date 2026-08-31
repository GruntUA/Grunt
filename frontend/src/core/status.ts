import type { BadgeVariants } from '@/components/ui/badge'
import type { DocType } from '@/types'

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
 * Resolve a document's status badge from its DocType `status_config`
 * (status field + colour indicators). Falls back to a bare `status` field
 * value with no colour. Returns null when there is nothing to show.
 */
export function resolveStatusBadge(
  dt: DocType | null | undefined,
  doc: Record<string, unknown> | null | undefined,
): StatusBadge | null {
  if (!doc) return null
  const cfg = dt?.status_config
  const field = cfg?.field || 'status'
  const val = doc[field]
  if (val == null || val === '') return null
  const ind = cfg?.indicators?.find((i) => i.value === String(val))
  return {
    label: ind?.label || String(val),
    variant: (ind && STATUS_VARIANT[ind.color]) || 'secondary',
  }
}
