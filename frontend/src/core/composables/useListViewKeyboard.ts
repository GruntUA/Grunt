import { ref, watch, ComputedRef, Ref } from 'vue'
import { useShortcut } from './useShortcuts'

/**
 * Manages keyboard navigation and shortcuts for list views.
 * Handles active row tracking (arrow keys, j/k), row selection (x),
 * opening documents (Enter, o), and bulk delete (Delete, Backspace).
 */
export function useListViewKeyboard(options: {
  rows: ComputedRef<Record<string, unknown>[]>
  selectedIds: Ref<string[]>
  allSelected: Ref<boolean> | ComputedRef<boolean>
  toggleSelection: (id: string) => void
  onOpenDoc: (row: Record<string, unknown>) => void
  onBulkDelete: () => Promise<void>
  onConfirmDelete: (title: string, subtitle: string) => Promise<boolean>
}) {
  const activeIndex = ref(0)

  // Reset active index when rows change
  watch(options.rows, () => {
    activeIndex.value = 0
  })

  // Navigate down: ArrowDown or 'j'
  useShortcut(['ArrowDown', 'j'], () => {
    if (!options.rows.value.length) return
    activeIndex.value = Math.min(activeIndex.value + 1, options.rows.value.length - 1)
  }, { preventDefault: true })

  // Navigate up: ArrowUp or 'k'
  useShortcut(['ArrowUp', 'k'], () => {
    if (!options.rows.value.length) return
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  }, { preventDefault: true })

  // Open current row: Enter or 'o'
  useShortcut(['Enter', 'o'], () => {
    if (options.rows.value[activeIndex.value]) {
      options.onOpenDoc(options.rows.value[activeIndex.value])
    }
  }, { preventDefault: true })

  // Toggle selection on current row: 'x'
  useShortcut(['x'], () => {
    if (options.rows.value[activeIndex.value]) {
      const rowId = String(options.rows.value[activeIndex.value].id)
      options.toggleSelection(rowId)
    }
  }, { preventDefault: true })

  // Delete selected rows: Delete or Backspace
  useShortcut(['Delete', 'Backspace'], async () => {
    if (options.selectedIds.value.length > 0 || options.allSelected.value) {
      const confirmed = await options.onConfirmDelete(
        'Видалити виділені документи?',
        'Обережно'
      )
      if (confirmed) {
        await options.onBulkDelete()
      }
    }
  }, { preventDefault: true })

  return {
    activeIndex,
  }
}
