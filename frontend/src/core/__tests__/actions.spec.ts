import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { actionButtonStyle, createActionRegistry } from '@/core/actions'

function setup(confirmResult = true) {
  const ctx = reactive({ dirty: false, canWrite: true })
  const confirm = vi.fn(async () => confirmResult)
  const registry = createActionRegistry(() => ctx, { confirm, translate: (s) => `t:${s}` })
  return { ctx, registry, confirm }
}

describe('action registry', () => {
  it('sorts by order, then insertion, per placement', () => {
    const { registry } = setup()
    registry.add({ id: 'b', label: 'B', placement: 'menu', order: 200, action: () => {} })
    registry.add({ id: 'a', label: 'A', placement: 'menu', order: 100, action: () => {} })
    registry.add({ id: 'c', label: 'C', placement: 'menu', order: 200, action: () => {} })
    registry.add({ id: 'save', label: 'Save', placement: 'primary', action: () => {} })
    expect(registry.resolved('menu').value.map((a) => a.id)).toEqual(['a', 'b', 'c'])
    expect(registry.resolved('primary').value.map((a) => a.label)).toEqual(['t:Save'])
  })

  it('re-adding an id replaces it; update and remove address it', () => {
    const { registry } = setup()
    registry.add({ id: 'x', label: 'One', action: () => {} })
    registry.add({ id: 'x', label: 'Two', action: () => {} })
    registry.update('x', { label: 'Three' })
    expect(registry.resolved('toolbar').value.map((a) => a.label)).toEqual(['t:Three'])
    registry.remove('x')
    expect(registry.resolved('toolbar').value).toEqual([])
  })

  it('re-evaluates visible / enabled reactively', () => {
    const { ctx, registry } = setup()
    registry.add({
      id: 'discard',
      label: 'Discard',
      visible: (c) => c.dirty,
      enabled: (c) => c.canWrite,
      action: () => {},
    })
    const toolbar = registry.resolved('toolbar')
    expect(toolbar.value).toEqual([])
    ctx.dirty = true
    expect(toolbar.value.map((a) => a.id)).toEqual(['discard'])
    ctx.canWrite = false
    expect(toolbar.value[0].disabled).toBe(true)
  })

  it('asks before running when confirm is set, and skips disabled actions', async () => {
    const run = vi.fn()
    const { registry, confirm } = setup(false)
    registry.add({ id: 'del', label: 'Delete', confirm: 'Sure?', action: run })
    await registry.run('del')
    expect(confirm).toHaveBeenCalledWith('t:Sure?')
    expect(run).not.toHaveBeenCalled()

    const off = setup()
    off.registry.add({ id: 'x', label: 'X', enabled: () => false, action: run })
    await off.registry.run('x')
    expect(run).not.toHaveBeenCalled()
  })

  it('a failing predicate hides the action instead of breaking the header', () => {
    const { registry } = setup()
    registry.add({ id: 'bad', label: 'Bad', visible: () => { throw new Error('boom') }, action: () => {} })
    expect(registry.resolved('toolbar').value).toEqual([])
  })
})

describe('styles', () => {
  it('maps tones to real Button variants', () => {
    expect(actionButtonStyle('destructive').variant).toBe('destructive')
    expect(actionButtonStyle('success')).toMatchObject({ variant: 'outline' })
    expect(actionButtonStyle('success').className).toContain('green')
    expect(actionButtonStyle(undefined).variant).toBe('outline')
  })
})
