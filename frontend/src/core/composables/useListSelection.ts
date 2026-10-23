import { ref, computed } from 'vue'

/**
 * The list's selection - always explicit document ids, across pages.
 * «Select all N» loads the ids of every matching document into it (see
 * DocTypeList), so bulk actions act on exactly what was selected.
 */
export function useListSelection() {
  const selectedIds = ref<string[]>([])

  function isSelected(id: string) {
    return selectedIds.value.includes(id)
  }

  function toggle(id: string) {
    if (selectedIds.value.includes(id)) {
      selectedIds.value = selectedIds.value.filter((s) => s !== id)
    } else {
      selectedIds.value = [...selectedIds.value, id]
    }
  }

  /** Header checkbox: ticks the given (page) ids, or - once all of them are ticked - clears the selection. */
  function toggleAll(pageIds: string[]) {
    if (pageIds.length && pageIds.every((id) => selectedIds.value.includes(id))) {
      clear()
    } else {
      selectedIds.value = [...new Set([...selectedIds.value, ...pageIds])]
    }
  }

  function setSelected(ids: string[]) {
    selectedIds.value = [...ids]
  }

  function clear() {
    selectedIds.value = []
  }

  const count = computed(() => selectedIds.value.length)

  return { selectedIds, count, isSelected, toggle, toggleAll, setSelected, clear }
}
