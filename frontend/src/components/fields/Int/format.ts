import type { ValueFormatter } from '@/core/formatValue'
import { formatNumber } from '@/core/currency'
import { formatBytes, isBytesField } from '@/core/bytes'

// `options: "Bytes"` marks a byte count - shown as `1.4 MB` instead of `1 468 006`.
const format: ValueFormatter = (value, field) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return isBytesField(field) ? formatBytes(n) : formatNumber(n)
}

export default format
