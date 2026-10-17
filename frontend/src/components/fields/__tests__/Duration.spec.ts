import { describe, it, expect, afterEach, vi } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import type { DocField } from '@/types'

vi.mock('@/core/datetime', () => ({ localeTag: () => 'uk' }))

import i18n from '@/plugins/i18n'
import Duration from '../Duration/Duration.vue'

const field = (extra: Partial<DocField> = {}) =>
  ({ fieldname: 'took', fieldtype: 'Duration', label: 'Took', ...extra }) as DocField

let w: VueWrapper | undefined
afterEach(() => { w?.unmount(); document.body.innerHTML = '' })

function mountDuration(modelValue: number | null, extra: Partial<DocField> = {}) {
  w = mount(Duration, {
    props: { field: field(extra), modelValue },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  return w
}

/** Presses the −/+ button of segment `i` (d, h, min, s[, ms]). */
async function press(w: VueWrapper, i: number, slot: 'increment' | 'decrement') {
  await flushPromises()
  const btn = w.findAll(`[data-slot="${slot}"]`)[i]!
  await btn.trigger('pointerdown')
  await btn.trigger('pointerup')
  await flushPromises()
}
const emitted = (w: VueWrapper) => w.emitted('update:modelValue')?.at(-1)?.[0]

describe('Duration field', () => {
  it('renders one segment per unit', () => {
    const w = mountDuration(9000)
    const inputs = w.findAll('input').map((i) => (i.element as HTMLInputElement).value)
    expect(inputs).toEqual(['0', '2', '30', '0'])
  })

  it('+ adds one unit to the total', async () => {
    const w = mountDuration(9000)
    await press(w, 2, 'increment') // minutes
    expect(emitted(w)).toBe(9060)
  })

  it('− borrows from the larger unit', async () => {
    const w = mountDuration(3600) // 1 h 0 min
    await press(w, 2, 'decrement')
    expect(emitted(w)).toBe(3540)
  })

  it('starts an empty value from zero', async () => {
    const w = mountDuration(null)
    await press(w, 1, 'increment') // hours
    expect(emitted(w)).toBe(3600)
  })

  it('has an ms segment for a millisecond field', () => {
    const w = mountDuration(715_667, { options: 'ms' })
    const inputs = w.findAll('input').map((i) => (i.element as HTMLInputElement).value)
    expect(inputs).toEqual(['0', '0', '11', '55', '667'])
  })

  it('shows only the readable value when read-only', () => {
    const w = mountDuration(715_667, { options: 'ms', read_only: true })
    const input = w.find('input').element as HTMLInputElement
    expect(input.value).toBe('11 min 56 s') // rounded to whole seconds
    expect(input.disabled).toBe(true)
  })
})
