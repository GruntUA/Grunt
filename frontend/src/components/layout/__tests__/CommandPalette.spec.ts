import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { reactive } from 'vue'

const h = vi.hoisted(() => ({
  push: vi.fn(),
  // The server matched "Acme" by a field the title doesn't contain.
  search: vi.fn(async () => ({ data: { data: [{ doctype: 'Customer', id: 'c1', display_title: 'Acme Corp' }] } })),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: h.push }) }))
vi.mock('@/core/api/client', () => ({ default: { get: h.search } }))
vi.mock('@/core/composables/useShortcuts', () => ({ useShortcut: () => {} }))
vi.mock('@/core/composables/useToast', () => ({ useToast: () => ({ success: () => {} }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => reactive({ logout: async () => {} }) }))
vi.mock('@/stores/app', () => ({
  useAppStore: () => reactive({ workspaces: [{ name: 'crm', label: 'CRM', items: [] }], active: null, loadAll: async () => {} }),
}))
vi.mock('@/stores/doctype', () => ({
  useDocTypeStore: () => reactive({ doctypes: [], cache: new Map(), loadAll: async () => {} }),
}))
const ui = vi.hoisted(() => ({ store: null as any }))
vi.mock('@/stores/ui', async () => {
  const { reactive } = await import('vue')
  ui.store = reactive({
    isCommandPaletteOpen: false,
    openCommandPalette() { ui.store.isCommandPaletteOpen = true },
    closeCommandPalette() { ui.store.isCommandPaletteOpen = false },
    toggleCommandPalette() { ui.store.isCommandPaletteOpen = !ui.store.isCommandPaletteOpen },
  })
  return { useUIStore: () => ui.store }
})

import CommandPalette from '../CommandPalette.vue'

// jsdom lacks these; reka's dialog and listbox call them.
Element.prototype.scrollIntoView ??= () => {}
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

const global = { plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })] }

const input = () => document.body.querySelector<HTMLInputElement>('[data-slot="command-input-wrapper"] input')!
const highlighted = () => document.body.querySelector<HTMLElement>('[data-slot="command-item"][data-highlighted]')

let w: VueWrapper | undefined
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  ui.store.isCommandPaletteOpen = false
  h.push.mockClear()
})

async function open() {
  w = mount(CommandPalette, { attachTo: document.body, global })
  ui.store.openCommandPalette()
  await flushPromises()
}

async function type(text: string) {
  input().value = text
  input().dispatchEvent(new Event('input'))
  await flushPromises()
}

describe('CommandPalette', () => {
  it('highlights the first quick action on open', async () => {
    await open()
    expect(highlighted()?.textContent).toBeTruthy()
  })

  it('keeps server hits the client filter would hide, and opens the first with Enter', async () => {
    await open()
    await type('acm')
    const titles = [...document.body.querySelectorAll('[data-slot="command-item"]')].map((el) => el.textContent)
    expect(titles.some((t) => t?.includes('Acme Corp'))).toBe(true)
    expect(highlighted()?.textContent).toContain('Acme Corp')

    input().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await flushPromises()
    expect(h.push).toHaveBeenCalledWith(expect.stringContaining('c1'))
  })

  it('moves the highlight with the arrow keys', async () => {
    await open()
    const first = highlighted()?.textContent
    input().dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    await flushPromises()
    expect(highlighted()?.textContent).not.toBe(first)
  })
})
