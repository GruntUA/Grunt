import { ref, computed } from 'vue'

export function useListSelection() {
  const selectedIds = ref<string[]>([])
  /** When true, ALL documents (across pages) are selected, not just visible ones */
  const allSelected = ref(false)

  function isSelected(id: string) {
    return allSelected.value || selectedIds.value.includes(id)
  }

  function toggle(id: string) {
    // If "select all" is active, switching to manual mode excluding this one
    if (allSelected.value) {
      allSelected.value = false
      // Can't easily exclude one from "all" — just deselect all
      selectedIds.value = []
      return
    }
    if (selectedIds.value.includes(id)) {
      selectedIds.value = selectedIds.value.filter((s) => s !== id)
    } else {
      selectedIds.value = [...selectedIds.value, id]
    }
  }

  function toggleAll(allIds: string[]) {
    if (selectedIds.value.length === allIds.length) {
      selectedIds.value = []
      allSelected.value = false
    } else {
      selectedIds.value = [...allIds]
      allSelected.value = false
    }
  }

  function selectAllDocuments() {
    allSelected.value = true
    selectedIds.value = []
  }

  function clear() {
    selectedIds.value = []
    allSelected.value = false
  }

  const count = computed(() => {
    if (allSelected.value) return -1 // signals "all"
    return selectedIds.value.length
  })

  return { selectedIds, allSelected, count, isSelected, toggle, toggleAll, selectAllDocuments, clear }
}
