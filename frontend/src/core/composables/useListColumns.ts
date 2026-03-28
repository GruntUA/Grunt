import { ref, computed } from 'vue'
import type { DocField } from '@/types'

export interface ListColumn {
  key: string
  label: string
  sortable: boolean
}

export function useListColumns(doctype: string, fields: () => DocField[]) {
  const hiddenCols = ref<string[]>([])

  // Restore from localStorage
  const saved = localStorage.getItem(`grunt_columns_${doctype}`)
  if (saved) hiddenCols.value = JSON.parse(saved) as string[]

  const allColumns = computed<ListColumn[]>(() => {
    const base = fields()
      .filter((f) => f.in_list_view && !f.hidden)
      .map((f) => ({ key: f.fieldname, label: f.label, sortable: true }))
    return base.length
      ? base
      : [
          { key: 'name', label: 'Назва', sortable: true },
          { key: 'created_at', label: 'Створено', sortable: false },
        ]
  })

  const visibleColumns = computed(() =>
    allColumns.value.filter((c) => !hiddenCols.value.includes(c.key)),
  )

  function toggleCol(key: string) {
    if (hiddenCols.value.includes(key)) {
      hiddenCols.value = hiddenCols.value.filter((k) => k !== key)
    } else {
      hiddenCols.value = [...hiddenCols.value, key]
    }
    localStorage.setItem(`grunt_columns_${doctype}`, JSON.stringify(hiddenCols.value))
  }

  return { allColumns, visibleColumns, hiddenCols, toggleCol }
}
