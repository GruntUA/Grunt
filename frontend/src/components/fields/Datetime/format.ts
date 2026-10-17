import type { ValueFormatter } from '@/core/formatValue'
import { formatDateTime } from '@/core/datetime'

const format: ValueFormatter = (value) => formatDateTime(String(value))

export default format
