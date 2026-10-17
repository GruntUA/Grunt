import type { ValueFormatter } from '@/core/formatValue'

const format: ValueFormatter = (value) =>
  value === true || value === 1 || value === '1' || value === 'true' ? '✓' : '✗'

export default format
