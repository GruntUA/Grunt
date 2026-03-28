import { ref } from 'vue'

export function useListSelection() {
  const selectedIds = ref<string[]>([])

  function isSelected(id: string) {
    return selectedIds.value.includes(id)
  }

  function toggle(id: string) {
    if (isSelected(id)) {
      selectedIds.value = selectedIds.value.filter((s) => s !== id)
    } else {
      selectedIds.value = [...selectedIds.value, id]
    }
  }

  function toggleAll(allIds: string[]) {
    if (selectedIds.value.length === allIds.length) {
      selectedIds.value = []
    } else {
      selectedIds.value = [...allIds]
    }
  }

  function clear() {
    selectedIds.value = []
  }

  return { selectedIds, isSelected, toggle, toggleAll, clear }
}
