import type { DocField } from '@/types'
import { formatValue } from '@/core/formatValue'
import { escapeHtml } from '@/lib/utils'

export function buildPopupTableHtml(
  row: Record<string, unknown>,
  popupFields: DocField[],
  labelField: string,
): string {
  const fieldRows = popupFields
    .filter((f) => f.fieldname !== labelField)
    .map((f) => {
      const val = escapeHtml(formatValue(f, row[f.fieldname]))
      return `<tr>
        <td class="popup-field-label">${escapeHtml(f.label ?? '')}</td>
        <td class="popup-field-value">${val}</td>
      </tr>`
    })
    .join('')

  return fieldRows ? `<table class="popup-fields">${fieldRows}</table>` : ''
}
