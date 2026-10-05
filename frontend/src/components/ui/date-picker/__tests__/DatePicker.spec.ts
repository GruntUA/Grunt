import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DatePicker from '../DatePicker.vue'
import { dateFormatSpec } from '@/core/datetime'

function typed(y: number, m: number, d: number): string {
  const parts = { y: String(y), m: String(m).padStart(2, '0'), d: String(d).padStart(2, '0') }
  const { order, sep } = dateFormatSpec()
  return order.map(p => parts[p]).join(sep)
}

describe('DatePicker', () => {
  it('Enter keeps the typed date — the blur that follows does not restore the old one', async () => {
    const wrapper = mount(DatePicker, {
      props: { modelValue: new Date(2205, 1, 17) },
      attachTo: document.body,
    })
    const input = wrapper.find('input')
    ;(input.element as HTMLInputElement).focus()
    await input.trigger('focus')
    await input.setValue(typed(2025, 2, 17))
    await input.trigger('keydown', { key: 'Enter' })

    const emitted = wrapper.emitted('update:modelValue') ?? []
    const last = emitted.at(-1)?.[0] as Date
    expect(last.getFullYear()).toBe(2025)
    expect(emitted.every(([d]) => (d as Date).getFullYear() === 2025)).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe(typed(2025, 2, 17))
    wrapper.unmount()
  })
})
