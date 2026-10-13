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
  linkSearch: vi.fn(async (_dt: string, q: string, filters?: Record<string, unknown>) => {
    const all = [
      { id: 'a', name: 'a', title: 'Alpha' },
      { id: 'b', name: 'b', title: 'Bravo' },
      { id: 'c', name: 'c', title: 'Charlie' },
    ]
    const names = filters?.name__in as string[] | undefined
    if (names) return all.filter((r) => names.includes(r.name))
    return all.filter((r) => !q || r.title.toLowerCase().includes(q.toLowerCase()))
  }),
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

describe('MultiLink on a flat DocType', () => {
  const options = () => [...document.body.querySelectorAll<HTMLElement>('[role="option"]')]
  const option = (text: string) => options().find((el) => el.textContent?.includes(text))!

  function mountFlat(modelValue: string[] = []) {
    api.isTree = false
    w = mount(MultiLink, { props: { field, modelValue }, attachTo: document.body, global })
    return w
  }

  it('shows tags with titles, not ids', async () => {
    mountFlat(['a', 'b'])
    await flushPromises()
    expect(w!.text()).toContain('Alpha')
    expect(w!.text()).toContain('Bravo')
    // ComboboxAnchor's default w-[200px] must not reach the field.
    expect(w!.find('[data-slot="combobox-anchor"]').classes()).not.toContain('w-[200px]')
  })

  it('adds a picked record and keeps the list open for the next pick', async () => {
    mountFlat(['a'])
    await flushPromises()
    await w!.find('input').trigger('focus')
    await flushPromises()
    expect(options().map((o) => o.textContent?.trim())).toEqual(['Bravo', 'Charlie']) // picked ones hidden
    option('Charlie').click()
    await flushPromises()
    expect(w!.emitted('update:modelValue')!.at(-1)).toEqual([['a', 'c']])
    expect(options().length).toBeGreaterThan(0)
  })

  it('picks the highlighted record with Enter', async () => {
    mountFlat()
    await flushPromises()
    const input = w!.find('input')
    await input.trigger('focus')
    await flushPromises()
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w!.emitted('update:modelValue')!.at(-1)![0]).toHaveLength(1)
  })

  it('never turns typed text into a tag', async () => {
    mountFlat(['a'])
    await flushPromises()
    const input = w!.find('input')
    ;(input.element as HTMLInputElement).value = 'zzz'
    await input.trigger('input')
    await input.trigger('keydown', { key: ',' })
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(w!.emitted('update:modelValue')).toBeUndefined()
  })

  it('removes a tag with its delete button', async () => {
    mountFlat(['a', 'b'])
    await flushPromises()
    // The × of the first tag ("Alpha").
    await w!.findAll('[data-reka-collection-item] button')[0].trigger('click')
    expect(w!.emitted('update:modelValue')!.at(-1)).toEqual([['b']])
  })
})
