import { computed } from 'vue'
import { useBuilderStore } from '@/stores/builder'

const SYSTEM_DATE_FIELDS = [
  { fieldname: 'created_at', label: 'Дата створення' },
  { fieldname: 'modified_at', label: 'Дата зміни' },
]

/**
 * Shared field-filtering utilities for view settings components.
 * All components that need filtered field lists (ListViewSettings,
 * KanbanSettings, etc.) use this composable to avoid duplicating
 * the filtering logic.
 */
export function useBuilderFields() {
  const builder = useBuilderStore()

  const dataFields = computed(() =>
    (builder.doctype?.fields ?? []).filter(
      (f) => !['Section', 'Column', 'Tab'].includes(f.fieldtype) && !!f.fieldname,
    ),
  )

  const selectFields = computed(() => dataFields.value.filter((f) => f.fieldtype === 'Select'))

  const linkFields = computed(() => dataFields.value.filter((f) => f.fieldtype === 'Link'))

  const dateFields = computed(() =>
    dataFields.value.filter((f) => ['Date', 'Datetime'].includes(f.fieldtype)),
  )

  const allDateFields = computed(() => [...SYSTEM_DATE_FIELDS, ...dateFields.value])

  return { builder, dataFields, selectFields, linkFields, dateFields, allDateFields }
}
