import { describe, it, expect } from 'vitest'
import { createActionRegistry } from '@/core/actions'
import { useListMapMenuItems } from '../useListMapMenuItems'

function registry() {
  return createActionRegistry(() => ({}), { confirm: async () => true })
}

describe('useListMapMenuItems', () => {
  it("registers a view's menu items as list menu actions", () => {
    const actions = registry()
    const { registerMapMenuItems } = useListMapMenuItems(actions)
    registerMapMenuItems([
      { label: 'A', action: () => {} },
      { label: 'B', action: () => {} },
    ])
    expect(actions.resolved('menu').value.map((a) => a.label)).toEqual(['A', 'B'])
  })

  it('unregisters only matching menu items', () => {
    const actions = registry()
    const keep = { label: 'Keep', action: () => {} }
    const remove = { label: 'Remove', action: () => {} }
    const { registerMapMenuItems, unregisterMapMenuItems } = useListMapMenuItems(actions)
    registerMapMenuItems([keep, remove])
    unregisterMapMenuItems([remove])
    expect(actions.resolved('menu').value.map((a) => a.label)).toEqual(['Keep'])
  })
})
