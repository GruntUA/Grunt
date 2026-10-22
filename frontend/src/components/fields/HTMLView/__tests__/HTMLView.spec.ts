import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import HTMLView from '../HTMLView.vue'
import { getNonPhysicalTypeSet } from '@/core/fieldRegistry'
import type { DocField } from '@/types'

const field = { fieldname: 'summary', fieldtype: 'HTMLView', label: 'Summary' } as DocField

describe('HTMLView field', () => {
  it('renders the stored markup', () => {
    const w = mount(HTMLView, {
      props: { field, modelValue: '<table><tbody><tr><td>B.1.1.2</td></tr></tbody></table>' },
    })
    expect(w.find('td').text()).toBe('B.1.1.2')
  })

  it('shows a dash when empty', () => {
    const w = mount(HTMLView, { props: { field, modelValue: null } })
    expect(w.text()).toBe('—')
  })

  it('has a column, unlike the static HTML field', () => {
    expect(getNonPhysicalTypeSet().has('HTMLView')).toBe(false)
  })
})
