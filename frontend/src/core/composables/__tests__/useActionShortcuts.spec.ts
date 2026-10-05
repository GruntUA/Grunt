import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import type { ActionRegistry } from '@/core/actions'
import { useActionShortcuts } from '@/core/composables/useActionShortcuts'

describe('useActionShortcuts', () => {
  it('commits a field that saves on blur before running the action, then refocuses it', async () => {
    let committed = 'old'
    let seenByAction: string | null = null
    const registry = {
      withShortcut: () => [{ shortcut: 'Mod+S', run: async () => { seenByAction = committed } }],
    } as unknown as ActionRegistry

    const Host = defineComponent({
      setup() {
        useActionShortcuts(registry)
        return () => h('input', { id: 'f', onBlur: () => { committed = 'typed' } })
      },
    })
    const wrapper = mount(Host, { attachTo: document.body })
    const input = wrapper.find('#f').element as HTMLInputElement
    input.focus()

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 's', code: 'KeyS', ctrlKey: true, bubbles: true }))
    await nextTick()
    await Promise.resolve()

    expect(seenByAction).toBe('typed')
    expect(document.activeElement).toBe(input)
    wrapper.unmount()
  })
})
