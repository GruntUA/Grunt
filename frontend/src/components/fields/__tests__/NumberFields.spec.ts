import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import type { DocField } from '@/types'

// Number fields format in the UI locale - Ukrainian: `1 234,5`.
vi.mock('@/core/datetime', () => ({ localeTag: () => 'uk' }))

import Int from '../Int/Int.vue'
import Float from '../Float/Float.vue'
import Currency from '../Currency/Currency.vue'
import Percent from '../Percent/Percent.vue'

const field = (fieldtype: string, extra: Partial<DocField> = {}) =>
  ({ fieldname: 'qty', fieldtype, label: 'Qty', ...extra }) as DocField

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

function mountField(cmp: any, props: Record<string, unknown>) {
  w = mount(cmp, { props: { modelValue: null, ...props }, attachTo: document.body })
  return w.find('input')
}

/** Types the text like a user (beforeinput validation included) and commits it. */
async function typeAndCommit(input: ReturnType<typeof mountField>, text: string) {
  const el = input.element as HTMLInputElement
  el.focus()
  for (const ch of text) {
    const key = new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true })
    el.dispatchEvent(key)
    if (key.defaultPrevented) continue // handled by the field (the decimal key)
    const before = new InputEvent('beforeinput', { data: ch, inputType: 'insertText', bubbles: true, cancelable: true })
    el.dispatchEvent(before)
    if (before.defaultPrevented) continue
    el.value += ch
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }
  await input.trigger('blur')
  await flushPromises()
}

const last = () => w!.emitted('update:modelValue')?.at(-1)?.[0]

describe('number fields on NumberField', () => {
  it('shows the value in the UI locale', async () => {
    const input = mountField(Float, { field: field('Float'), modelValue: 1234.5 })
    await flushPromises()
    expect((input.element as HTMLInputElement).value.replace(/\s/g, ' ')).toBe('1 234,5')
  })

  it('takes a decimal comma, and the period key types it too', async () => {
    let input = mountField(Float, { field: field('Float') })
    await typeAndCommit(input, '1,5')
    expect(last()).toBe(1.5)
    w!.unmount()
    input = mountField(Float, { field: field('Float') })
    await typeAndCommit(input, '2.25')
    expect(last()).toBe(2.25)
  })

  it('Int drops the fraction, Currency rounds to cents', async () => {
    await typeAndCommit(mountField(Int, { field: field('Int') }), '7')
    expect(last()).toBe(7)
    w!.unmount()
    await typeAndCommit(mountField(Currency, { field: field('Currency') }), '10.456')
    expect(last()).toBe(10.46)
  })

  it('Percent stores the number as typed, not a fraction', async () => {
    await typeAndCommit(mountField(Percent, { field: field('Percent') }), '25')
    expect(last()).toBe(25)
  })

  it('emptying the field stores null', async () => {
    const input = mountField(Int, { field: field('Int'), modelValue: 5 })
    await flushPromises()
    ;(input.element as HTMLInputElement).value = ''
    await input.trigger('input')
    await input.trigger('blur')
    await flushPromises()
    expect(last()).toBeNull()
  })

  it('the +/- buttons step the value', async () => {
    mountField(Int, { field: field('Int'), modelValue: 5 })
    await flushPromises()
    await w!.find('[data-slot="increment"]').trigger('pointerdown')
    await w!.find('[data-slot="increment"]').trigger('pointerup')
    await flushPromises()
    expect(last()).toBe(6)
  })
})
