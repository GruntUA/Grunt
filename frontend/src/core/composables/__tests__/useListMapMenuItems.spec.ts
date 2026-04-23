import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useListMapMenuItems } from '../useListMapMenuItems'

describe('useListMapMenuItems', () => {
  it('registers menu items', () => {
    const listMenuItems = ref([])
    const { registerMapMenuItems } = useListMapMenuItems(listMenuItems)
    const items = [
      { label: 'A', action: () => {} },
      { label: 'B', action: () => {} },
    ]

    registerMapMenuItems(items)

    expect(listMenuItems.value).toEqual(items)
  })

  it('unregisters only matching menu items', () => {
    const keep = { label: 'Keep', action: () => {} }
    const remove = { label: 'Remove', action: () => {} }
    const listMenuItems = ref([keep, remove])
    const { unregisterMapMenuItems } = useListMapMenuItems(listMenuItems)

    unregisterMapMenuItems([remove])

    expect(listMenuItems.value).toEqual([keep])
  })
})