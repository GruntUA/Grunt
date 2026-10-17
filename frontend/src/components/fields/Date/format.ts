import type { ValueFormatter } from '@/core/formatValue'
import { formatDate } from '@/core/datetime'

const format: ValueFormatter = (value) => formatDate(String(value))

export default format
