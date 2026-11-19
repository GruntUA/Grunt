import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  // jsdom lacks matchMedia; something in the component's import chain reads it on load.
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
})
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const list = vi.fn()
const save = vi.fn()
vi.mock('@/core/api/savedFilters', () => ({
  savedFiltersApi: { list: (...a: unknown[]) => list(...a), save: (...a: unknown[]) => save(...a), remove: vi.fn() },
}))

import FilterBar from '../FilterBar.vue'
import { i18n } from '@/plugins/i18n'

const F = [{ fieldname: 'status', op: '=', value: 'Open' }]
let w: VueWrapper | undefined

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
})
afterEach(() => { w?.unmount(); list.mockReset(); save.mockReset() })

describe('FilterBar saved filters', () => {
  it('sends local presets up once, then drops the local copy', async () => {
    localStorage.setItem('grunt_filter_presets_Task', JSON.stringify([
      { name: 'Old', filters: F },
      { name: 'Kept', filters: F },
    ]))
    list.mockResolvedValue([{ name: 'a', title: 'Kept', filters: F, shared_with: 'Nobody', roles: [], mine: true }])
    save.mockImplementation(async (_dt: string, title: string) => ({ name: 'b', title, filters: F, shared_with: 'Nobody', roles: [], mine: true }))
    w = mount(FilterBar, { props: { fields: [], doctype: 'Task' }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith('Task', 'Old', F)
    expect(localStorage.getItem('grunt_filter_presets_Task')).toBeNull()
  })
})
