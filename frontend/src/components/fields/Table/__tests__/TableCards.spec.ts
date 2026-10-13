import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import type { DocField } from '@/types'
import i18n from '@/plugins/i18n'

vi.hoisted(() => {
  // jsdom lacks matchMedia; something in the field's import chain reads it on load.
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as any
})

const child = vi.hoisted(() => ({
  name: 'OrderItem',
  fields: [
    { fieldname: 'item', fieldtype: 'Data', label: 'Item', in_list_view: true },
    { fieldname: 'qty', fieldtype: 'Int', label: 'Qty', in_list_view: true },
    { fieldname: 'note', fieldtype: 'Data', label: 'Note', in_list_view: true },
  ],
}))

vi.mock('@/stores/doctype', () => ({ useDocTypeStore: () => ({ get: async () => child }) }))
// Phone width: the table renders as cards.
vi.mock('@/components/views/list/useCardLayout', () => ({ useCardLayout: () => ref(true) }))

import Table from '../Table.vue'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

const field = { fieldname: 'items', fieldtype: 'Table', label: 'Items', options: 'OrderItem' } as DocField
const rows = [
  { name: 'r1', item: 'Bolt', qty: 3, note: '' },
  { name: 'r2', item: 'Nut', qty: 7, note: 'spare' },
]

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

describe('Table field on a phone', () => {
  it('shows one card per row: the first column as title, the rest as label/value pairs', async () => {
    w = mount(Table, { props: { field, modelValue: rows }, attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('table').exists()).toBe(false)
    const cards = w.findAll('[data-slot="card"]')
    expect(cards).toHaveLength(2)
    expect(cards[0].text()).toContain('Bolt')
    expect(cards[0].text()).toContain('Qty')
    expect(cards[0].text()).not.toContain('Note') // empty values are left out
    expect(cards[1].text()).toContain('spare')
  })

  it('opens the row sheet on tap', async () => {
    w = mount(Table, { props: { field, modelValue: rows }, attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()
    await w.findAll('[data-slot="card"]')[1].trigger('click')
    await flushPromises()
    const sheet = document.body.querySelector('[data-slot="sheet-content"]')!
    expect(sheet.textContent).toContain('Row 2') // the tapped row (field editors load lazily, not here)
  })
})
