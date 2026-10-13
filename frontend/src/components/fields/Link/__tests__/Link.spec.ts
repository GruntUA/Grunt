import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { DocField } from '@/types'

const api = vi.hoisted(() => ({
  linkSearch: vi.fn(async (_doctype: string, q: string) =>
    [
      { id: 'c1', name: 'c1', title: 'Acme Corp' },
      { id: 'c2', name: 'c2', title: 'Beta Ltd' },
    ].filter((r) => !q || r.title.toLowerCase().includes(q.toLowerCase())),
  ),
}))

vi.mock('@/core/api', () => ({
  docsApi: { linkSearch: api.linkSearch, getTree: async () => [] },
  metaApi: { get: async () => ({ title_field: 'company_name', is_tree: false, fields: [] }) },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { workspaceName: 'crm' } }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

import Link from '../Link.vue'

// jsdom lacks these; reka's popper and listbox call them.
Element.prototype.scrollIntoView ??= () => {}
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

const field = { fieldname: 'customer', fieldtype: 'Link', label: 'Customer', options: 'Customer' } as DocField

const global = {
  plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })],
}

const options = () => [...document.body.querySelectorAll<HTMLElement>('[role="option"]')]
const option = (text: string) => options().find((el) => el.textContent?.includes(text))!

let w: VueWrapper | undefined
beforeEach(() => api.linkSearch.mockClear())
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
})

function mountLink(props: Record<string, unknown> = {}) {
  w = mount(Link, { props: { field, modelValue: null, ...props }, attachTo: document.body, global })
  return w
}

describe('Link field', () => {
  it('shows the linked title from the parent doc without searching', async () => {
    mountLink({ modelValue: 'c1', doc: { customer: 'c1', customer__label: 'Acme Corp' } })
    await flushPromises()
    expect((w!.find('input').element as HTMLInputElement).value).toBe('Acme Corp')
    expect(api.linkSearch).not.toHaveBeenCalled()
    // ComboboxAnchor's default w-[200px] must not reach the field.
    expect(w!.find('[data-slot="combobox-anchor"]').classes()).not.toContain('w-[200px]')
  })

  it('opens the default list on focus and selects a record', async () => {
    mountLink()
    await flushPromises()
    await w!.find('input').trigger('focus')
    await flushPromises()
    expect(api.linkSearch).toHaveBeenCalledWith('Customer', '', {})
    expect(options().map((o) => o.textContent?.trim())).toEqual(expect.arrayContaining(['Acme Corp', 'Beta Ltd']))

    option('Beta Ltd').click()
    await flushPromises()
    expect(w!.emitted('update:modelValue')?.at(-1)).toEqual(['c2'])
    expect((w!.find('input').element as HTMLInputElement).value).toBe('Beta Ltd')
  })

  it('searches the server with the typed text', async () => {
    vi.useFakeTimers()
    try {
      mountLink()
      await flushPromises()
      const input = w!.find('input')
      ;(input.element as HTMLInputElement).value = 'acm'
      await input.trigger('input')
      vi.advanceTimersByTime(350)
      await flushPromises()
      expect(api.linkSearch).toHaveBeenLastCalledWith('Customer', 'acm', {})
      expect(options().some((o) => o.textContent?.includes('Acme Corp'))).toBe(true)
      expect(options().some((o) => o.textContent?.includes('Beta Ltd'))).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('offers to create a record named after the typed text', async () => {
    vi.useFakeTimers()
    try {
      mountLink()
      await flushPromises()
      const input = w!.find('input')
      ;(input.element as HTMLInputElement).value = 'Gamma'
      await input.trigger('input')
      vi.advanceTimersByTime(350)
      await flushPromises()
      option('Create').click()
      await flushPromises()
      expect(w!.emitted('create-new')?.at(-1)).toEqual(['Customer', 'Gamma'])
      expect(w!.emitted('update:modelValue')).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })

  it('picks a record with the keyboard', async () => {
    mountLink()
    await flushPromises()
    const input = w!.find('input')
    await input.trigger('focus')
    await flushPromises()
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w!.emitted('update:modelValue')?.at(-1)?.[0]).toMatch(/^c[12]$/)
  })

  it('restores the picked title when typing is abandoned with Escape', async () => {
    vi.useFakeTimers()
    try {
      mountLink({ modelValue: 'c1', doc: { customer: 'c1', customer__label: 'Acme Corp' } })
      await flushPromises()
      const input = w!.find('input')
      ;(input.element as HTMLInputElement).value = 'zzz'
      await input.trigger('input')
      vi.advanceTimersByTime(350)
      await flushPromises()
      await input.trigger('keydown', { key: 'Escape' })
      await flushPromises()
      expect((input.element as HTMLInputElement).value).toBe('Acme Corp')
      expect(w!.emitted('update:modelValue')).toBeUndefined()
    } finally {
      vi.useRealTimers()
    }
  })

  it('clears the value', async () => {
    mountLink({ modelValue: 'c1', doc: { customer: 'c1', customer__label: 'Acme Corp' } })
    await flushPromises()
    await w!.find('button[aria-label="Clear"]').trigger('mousedown')
    expect(w!.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })
})
