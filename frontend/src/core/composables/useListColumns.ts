import { ref, computed } from 'vue'
import type { DocField } from '@/types'

export interface ListColumn {
  key: string
  label: string
  sortable: boolean
}

const STRUCTURAL = new Set(['Section', 'Column', 'Tab', 'Table', 'MultiLink'])

export function useListColumns(doctype: string, fields: () => DocField[], titleField?: () => string | undefined) {
  const storageKey = `grunt_columns_v2_${doctype}`
  const saved = localStorage.getItem(storageKey)
  const _savedKeys = ref<string[] | null>(saved ? (JSON.parse(saved) as string[]) : null)

  // All non-structural fields that can be shown as columns
  const allAvailableColumns = computed<ListColumn[]>(() =>
    fields()
      .filter(f => !STRUCTURAL.has(f.fieldtype) && !f.hidden)
      .map(f => ({ key: f.fieldname, label: f.label, sortable: true }))
  )

  // Default visible = in_list_view fields
  const defaultKeys = computed<string[]>(() => {
    let cols = fields().filter(f => f.in_list_view && !f.hidden).map(f => f.fieldname)
    if (!cols.length) cols = ['id']

    const tf = titleField?.()
    if (tf && cols.includes(tf)) {
      // Move title field to front
      cols = [tf, ...cols.filter(c => c !== tf)]
    }

    return cols
  })

  // Currently visible keys (saved or default)
  const visibleKeys = computed<string[]>(() => _savedKeys.value ?? defaultKeys.value)

  // Visible columns in order
  const visibleColumns = computed<ListColumn[]>(() =>
    visibleKeys.value
      .map(key => allAvailableColumns.value.find(c => c.key === key))
      .filter((c): c is ListColumn => c !== undefined)
  )

  function isVisible(key: string): boolean {
    return visibleKeys.value.includes(key)
  }

  function toggleCol(key: string) {
    const current = visibleKeys.value
    const next = current.includes(key)
      ? current.filter(k => k !== key)
      : [...current, key]
    _savedKeys.value = next
    localStorage.setItem(storageKey, JSON.stringify(next))
  }

  function reorderCols(oldIndex: number, newIndex: number) {
    const current = [...visibleKeys.value]
    const [moved] = current.splice(oldIndex, 1)
    current.splice(newIndex, 0, moved)
    _savedKeys.value = current
    localStorage.setItem(storageKey, JSON.stringify(current))
  }

  // True when the user has saved a custom selection (differs from defaults)
  const isCustomized = computed(() => _savedKeys.value !== null)

  return { allAvailableColumns, visibleColumns, visibleKeys, defaultKeys, isVisible, toggleCol, reorderCols, isCustomized }
}
