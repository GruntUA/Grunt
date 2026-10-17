import type { ValueFormatter } from '@/core/formatValue'

/** `★★★½☆ 3.5` - out of 5. Anything outside 0-5 (e.g. a report total) stays a number. */
const format: ValueFormatter = (value) => {
  const n = Number(value)
  if (Number.isNaN(n) || n < 0 || n > 5) return String(value)
  const full = Math.floor(n)
  const half = n - full >= 0.5
  return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(5 - full - (half ? 1 : 0)) + ` ${n}`
}

export default format
