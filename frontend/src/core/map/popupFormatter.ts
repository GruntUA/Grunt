import type { DocField } from '@/types'

export function formatPopupValue(value: unknown, fieldtype: string): string {
  if (value === null || value === undefined || value === '') return '—'
  if (fieldtype === 'Check') return value ? '✓' : '✗'
  if (fieldtype === 'Rating') {
    const n = Number(value)
    if (Number.isNaN(n)) return '—'
    const full = Math.floor(n)
    const half = n - full >= 0.5
    const empty = 5 - full - (half ? 1 : 0)
    return '★'.repeat(full) + (half ? '½' : '') + '☆'.repeat(empty) + ` ${n}`
  }
  if (fieldtype === 'Float' && typeof value === 'number') return value.toFixed(2).replace(/\.?0+$/, '')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function buildPopupTableHtml(
  row: Record<string, unknown>,
  popupFields: DocField[],
  labelField: string,
): string {
  const fieldRows = popupFields
    .filter((f) => f.fieldname !== labelField)
    .map((f) => {
      const val = formatPopupValue(row[f.fieldname], f.fieldtype)
      return `<tr>
        <td class="popup-field-label">${f.label}</td>
        <td class="popup-field-value">${val}</td>
      </tr>`
    })
    .join('')

  return fieldRows ? `<table class="popup-fields">${fieldRows}</table>` : ''
}
