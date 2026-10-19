/** Byte counts as human-readable sizes (`512 B`, `1.4 MB`, `23 GB`). */

import i18n from '@/plugins/i18n'
import { formatNumber } from '@/core/currency'

const UNITS = ['KB', 'MB', 'GB', 'TB']

/** `bytes` with a binary unit: one decimal below 10, whole numbers above. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—'
  const t = i18n.global.t
  if (Math.abs(bytes) < 1024) return `${bytes} ${t('B')}`
  let value = bytes / 1024
  let i = 0
  while (Math.abs(value) >= 1024 && i < UNITS.length - 1) {
    value /= 1024
    i++
  }
  const digits = Math.abs(value) < 10 ? 1 : 0
  return `${formatNumber(Number(value.toFixed(digits)))} ${t(UNITS[i])}`
}

/** True for an Int field that stores a byte count (`options: "Bytes"`). */
export function isBytesField(field: { options?: string | null }): boolean {
  return field.options === 'Bytes'
}
