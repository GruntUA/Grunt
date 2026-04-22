import { computed, type Ref } from 'vue'
import type { DocField } from '@/types'

const POPUP_SKIP_TYPES = new Set([
  'Section',
  'Column',
  'Tab',
  'Table',
  'MultiLink',
  'LongText',
  'RichText',
  'Code',
  'Geolocation',
  'Attach',
  'Image',
  'Signature',
  'JSON',
])

interface UseMapPopupFieldsParams {
  doctypeName: Ref<string>
  fields: Ref<DocField[]>
  geoField: Ref<string>
}

export function useMapPopupFields({ doctypeName, fields, geoField }: UseMapPopupFieldsParams) {
  const popupFields = computed(() => {
    const storageKey = `grunt_columns_v2_${doctypeName.value}`
    const saved = localStorage.getItem(storageKey)
    const savedKeys: string[] | null = saved ? (JSON.parse(saved) as string[]) : null

    const allFields = fields.value.filter(
      (f) => !POPUP_SKIP_TYPES.has(f.fieldtype) && !f.hidden && f.fieldname !== geoField.value,
    )

    if (savedKeys?.length) {
      // Respect user's column order/selection
      return savedKeys
        .map((key) => allFields.find((f) => f.fieldname === key))
        .filter((f): f is NonNullable<typeof f> => f !== undefined)
    }

    // Fallback: in_list_view fields
    const listFields = allFields.filter((f) => f.in_list_view)
    return listFields.length ? listFields : allFields.slice(0, 5)
  })

  return {
    popupFields,
  }
}
