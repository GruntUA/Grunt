import type { ValueFormatter } from '@/core/formatValue'

/** `50.45010, 30.52340` */
const format: ValueFormatter = (value) => {
  if (typeof value === 'object' && value !== null && 'lat' in value && 'lng' in value) {
    const { lat, lng } = value as { lat: unknown; lng: unknown }
    return `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}`
  }
  return String(value)
}

export default format
