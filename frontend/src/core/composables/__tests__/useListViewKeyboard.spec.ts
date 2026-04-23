import { describe, it, expect, vi, beforeEach } from 'vitest'
import { computed, nextTick, ref } from 'vue'

const shortcutHandlers = new Map<string, () => void | Promise<void>>()

vi.mock('../useShortcuts', () => ({
  useShortcut: (keys: string | string[], handler: () => void | Promise<void>) => {
    const normalized = Array.isArray(keys) ? keys : [keys]
    normalized.forEach((key) => shortcutHandlers.set(key, handler))
  },
}))

import { useListViewKeyboard } from '../useListViewKeyboard'

describe('useListViewKeyboard', () => {
  beforeEach(() => {
    shortcutHandlers.clear()
  })

  function setup() {
    const rowsRef = ref<Record<string, unknown>[]>([
      { id: 'a', title: 'A' },
      { id: 'b', title: 'B' },
    ])
    const selectedIds = ref<string[]>([])
    const allSelected = ref(false)
    const onOpenDoc = vi.fn()
    const onBulkDelete = vi.fn().mockResolvedValue(undefined)
    const onConfirmDelete = vi.fn().mockResolvedValue(true)
    const toggleSelection = vi.fn()

    const keyboard = useListViewKeyboard({
      rows: computed(() => rowsRef.value),
      selectedIds,
      allSelected,
      toggleSelection,
      onOpenDoc,
      onBulkDelete,
      onConfirmDelete,
    })

    return {
      rowsRef,
      selectedIds,
      allSelected,
      onOpenDoc,
      onBulkDelete,
      onConfirmDelete,
      toggleSelection,
      ...keyboard,
    }
  }

  it('moves active index down and up with shortcuts', () => {
    const { activeIndex } = setup()

    shortcutHandlers.get('ArrowDown')?.()
    expect(activeIndex.value).toBe(1)

    shortcutHandlers.get('ArrowUp')?.()
    expect(activeIndex.value).toBe(0)
  })

  it('opens the active row on Enter', () => {
    const { onOpenDoc } = setup()

    shortcutHandlers.get('j')?.()
    shortcutHandlers.get('Enter')?.()

    expect(onOpenDoc).toHaveBeenCalledWith({ id: 'b', title: 'B' })
  })

  it('toggles selection for the active row on x', () => {
    const { toggleSelection } = setup()

    shortcutHandlers.get('x')?.()

    expect(toggleSelection).toHaveBeenCalledWith('a')
  })

  it('resets active index when rows change', async () => {
    const { activeIndex, rowsRef } = setup()

    shortcutHandlers.get('ArrowDown')?.()
    expect(activeIndex.value).toBe(1)

    rowsRef.value = [{ id: 'c', title: 'C' }]
    await nextTick()

    expect(activeIndex.value).toBe(0)
  })

  it('confirms and deletes selected rows', async () => {
    const { selectedIds, onConfirmDelete, onBulkDelete } = setup()
    selectedIds.value = ['a']

    await shortcutHandlers.get('Delete')?.()

    expect(onConfirmDelete).toHaveBeenCalledWith('Видалити виділені документи?', 'Обережно')
    expect(onBulkDelete).toHaveBeenCalled()
  })

  it('does not trigger delete without selection', async () => {
    const { onConfirmDelete, onBulkDelete } = setup()

    await shortcutHandlers.get('Delete')?.()

    expect(onConfirmDelete).not.toHaveBeenCalled()
    expect(onBulkDelete).not.toHaveBeenCalled()
  })
})