import type { ValueFormatter } from '@/core/formatValue'
import { durationUnit, formatDuration } from '@/core/duration'

const format: ValueFormatter = (value, field) => formatDuration(value, durationUnit({ options: field.options }))

export default format
