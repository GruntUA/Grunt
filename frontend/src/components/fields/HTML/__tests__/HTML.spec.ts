import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HTML from '../HTML.vue'
import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import type { DocField } from '@/types'

describe('HTML field', () => {
  it('renders the options markup', () => {
    const field = { fieldname: 'hint', fieldtype: 'HTML', label: 'Hint', options: '<p>Вкажіть <b>ЄДРПОУ</b></p>' } as DocField
    const w = mount(HTML, { props: { field, modelValue: undefined, doc: { a: 1 } } })
    expect(w.find('b').text()).toBe('ЄДРПОУ')
    expect(w.attributes('doc')).toBeUndefined()
  })

  it('has no column, like Button / Table / layout types', () => {
    const set = getNonPhysicalTypeSet()
    for (const t of ['HTML', 'Button', 'Table', 'MultiLink', 'Section']) expect(set.has(t)).toBe(true)
    expect(set.has('Data')).toBe(false)
  })
})
