import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { DocField } from '@/types'

const api = vi.hoisted(() => ({
  isTree: true,
  getTree: vi.fn(async () => [
    {
      id: 'press',
      label: 'Прес-центр',
      children: [{ id: 'news', label: 'Новини' }],
    },
    { id: 'economy', label: 'Економіка' },
  ]),
  linkSearch: vi.fn(async () => []),
}))

vi.mock('@/core/api', () => ({
  docsApi: { getTree: api.getTree, linkSearch: api.linkSearch },
  metaApi: { get: async () => ({ title_field: 'label', is_tree: api.isTree }) },
}))

import MultiLink from '../MultiLink.vue'

// jsdom lacks these; reka's dialog calls them.
Element.prototype.scrollIntoView ??= () => {}
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

const field = {
  fieldname: 'sections',
  fieldtype: 'MultiLink',
  label: 'Розділи',
  options: 'WebsiteMenuItem',
  link_filters: '{"menu": "mlt_portal"}',
} as DocField

const rows = () => [...document.body.querySelectorAll<HTMLElement>('[data-tree-row]')]
const row = (text: string) => rows().find((el) => el.textContent?.includes(text))!
const button = (text: string) =>
  [...document.body.querySelectorAll<HTMLElement>('button')].find((el) => el.textContent?.trim() === text)!

const global = {
  plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })],
}

let w: VueWrapper | undefined
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
  api.isTree = true
})

describe('MultiLink on a tree DocType', () => {
  it('picks several nodes in the tree dialog', async () => {
    w = mount(MultiLink, { props: { field, modelValue: ['economy'] }, attachTo: document.body, global })
    await flushPromises()
    expect(w.find('input').exists()).toBe(false)

    await w.find('button[aria-label="Choose from the tree"]').trigger('click')
    await flushPromises()

    expect(api.getTree).toHaveBeenCalledWith('WebsiteMenuItem', { quickFilters: { menu: 'mlt_portal' } })
    // Roots are expanded, so the nested section is offered right away.
    expect(rows().map((el) => el.dataset.key)).toEqual(['press', 'news', 'economy'])
    expect(row('Економіка').getAttribute('aria-selected')).toBe('true')

    row('Новини').click()
    row('Економіка').click()
    await flushPromises()
    expect(w.emitted('update:modelValue')).toBeUndefined() // nothing until confirmed

    button('Done').click()
    await flushPromises()
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual([['news']])
  })

  it('keeps the search input for a flat DocType', async () => {
    api.isTree = false
    w = mount(MultiLink, { props: { field, modelValue: [] }, attachTo: document.body, global })
    await flushPromises()
    expect(w.find('input').exists()).toBe(true)
    expect(w.find('button[aria-label="Choose from the tree"]').exists()).toBe(false)
  })
})
