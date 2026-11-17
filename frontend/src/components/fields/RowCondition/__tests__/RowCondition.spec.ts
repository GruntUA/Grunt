import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { DocField } from '@/types'

vi.mock('@/core/api/meta', () => ({
  metaApi: {
    get: vi.fn(async () => ({
      fields: [{ fieldname: 'lead', label: 'Lead', fieldtype: 'Data' }],
    })),
  },
}))

import i18n from '@/plugins/i18n'
import { PARENT_DOC } from '@/components/fields/Table/parentDoc'
import RowCondition from '../RowCondition.vue'

const field = { fieldname: 'match', fieldtype: 'RowCondition', label: 'Row condition' } as DocField
const parent = {
  fields: [
    { fieldname: 'title', label: 'Title', fieldtype: 'Data' },
    { fieldname: 'team', label: 'Team', fieldtype: 'Link', options: 'Team' },
    { fieldname: 'sec', label: 'Section', fieldtype: 'Section' },
  ],
}

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

function mountIt(modelValue: string | null) {
  w = mount(RowCondition, {
    props: { field, modelValue },
    global: { plugins: [i18n], provide: { [PARENT_DOC as symbol]: computed(() => parent) } },
    attachTo: document.body,
  })
  return w
}
const emitted = (w: VueWrapper) => w.emitted('update:modelValue')?.at(-1)?.[0]

describe('RowCondition field', () => {
  it('lists the fields of the DocType being edited, not its layout', () => {
    const w = mountIt(null)
    const options = w.findAll('select')[0]!.findAll('option').map((o) => o.element.value)
    expect(options).toContain('title')
    expect(options).toContain('owner')
    expect(options).not.toContain('sec')
  })

  it('builds the condition from the pickers', async () => {
    const w = mountIt(null)
    await w.findAll('select')[0]!.setValue('title')
    expect(emitted(w)).toBe('title == user')
  })

  it('a Link field offers the target fields', async () => {
    const w = mountIt('team == user')
    await flushPromises()
    const selects = w.findAll('select')
    expect(selects[1]!.findAll('option').map((o) => o.element.value)).toContain('lead')
    await selects[1]!.setValue('lead')
    expect(emitted(w)).toBe('team.lead == user')
  })

  it('a value with both quote kinds is refused, not altered', async () => {
    const w = mountIt("title == 'x'")
    const before = w.emitted('update:modelValue')?.length ?? 0
    await w.find('input').setValue(`Bob's "Draft"`)
    expect(w.emitted('update:modelValue')?.length ?? 0).toBe(before)
    expect(w.text()).toContain('quotes')
  })

  it('text outside the builder opens as text', () => {
    const w = mountIt("a == 'x' and b == 'y'")
    expect(w.find('select').exists()).toBe(false)
    expect((w.find('input').element as HTMLInputElement).value).toBe("a == 'x' and b == 'y'")
  })
})
