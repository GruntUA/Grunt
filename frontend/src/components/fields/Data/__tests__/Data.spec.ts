import { describe, it, expect, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import Data from '../Data.vue'
import type { DocField } from '@/types'

const field = (over: Partial<DocField> = {}) =>
  ({ fieldname: 'position', fieldtype: 'Data', label: 'Position', ...over }) as DocField

// jsdom lacks these; reka's popper/listbox call them.
Element.prototype.scrollIntoView ??= () => {}
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any

let w: VueWrapper | undefined
afterEach(() => {
  w?.unmount()
  document.body.innerHTML = ''
})

const items = () => [...document.body.querySelectorAll('[role="option"]')].map((el) => el.textContent?.trim())

describe('Data field autocomplete', () => {
  it('is a plain input without options', () => {
    w = mount(Data, { props: { field: field(), modelValue: '' } })
    expect(w.find('input').attributes('role')).toBeUndefined()
  })

  it('suggests options filtered by the typed text, keeps free text', async () => {
    w = mount(Data, {
      props: { field: field({ options: 'Інженер\nГоловний інженер\nБухгалтер' }), modelValue: 'інж' },
      attachTo: document.body,
    })
    const input = w.find('input')
    expect(input.attributes('role')).toBe('combobox')

    await input.trigger('focus')
    await flushPromises()
    expect(items()).toEqual(['Інженер', 'Головний інженер'])

    await input.setValue('Прибиральник')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['Прибиральник'])
  })

  it('emits the picked suggestion', async () => {
    w = mount(Data, {
      props: { field: field({ options: 'Інженер\nБухгалтер' }), modelValue: '' },
      attachTo: document.body,
    })
    await w.find('input').trigger('focus')
    await flushPromises()
    const opt = [...document.body.querySelectorAll<HTMLElement>('[role="option"]')].find((el) => el.textContent?.includes('Бухгалтер'))!
    opt.click()
    await flushPromises()
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['Бухгалтер'])
  })

  it('has no suggestions when read-only', () => {
    w = mount(Data, { props: { field: field({ options: 'A', read_only: true }), modelValue: 'x' } })
    expect(w.find('[role="combobox"]').exists()).toBe(false)
  })
})
