import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { parseRelativeDays, relativeDateValue } from '@/core/relativeDate'
import RelativeDateFilter from '@/components/common/RelativeDateFilter.vue'

describe('relative date values', () => {
  it('reads today, today-N and today+N as days, like the server', () => {
    expect(parseRelativeDays('today')).toBe(0)
    expect(parseRelativeDays('today-30')).toBe(-30)
    expect(parseRelativeDays(' Today + 7 ')).toBe(7)
    expect(parseRelativeDays('2026-01-15')).toBeNull()
    expect(parseRelativeDays('todays')).toBeNull()
    expect(parseRelativeDays('')).toBeNull()
  })

  it('writes days as a filter value', () => {
    expect(relativeDateValue(0)).toBe('today')
    expect(relativeDateValue(-30)).toBe('today-30')
    expect(relativeDateValue(7)).toBe('today+7')
    expect(relativeDateValue(Number.NaN)).toBe('today')
    expect(relativeDateValue(100000)).toBe('today+99999')
    expect(relativeDateValue(-100000)).toBe('today-99999')
  })
})

describe('RelativeDateFilter', () => {
  const slots = { absolute: '<input data-test="picker" />' }
  const global = {
    plugins: [createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false })],
  }

  it('shows the field picker for a fixed date', () => {
    const w = mount(RelativeDateFilter, { props: { modelValue: '2026-01-15' }, slots, global })
    expect(w.find('[data-test="picker"]').exists()).toBe(true)
    expect(w.find('input[type="number"]').exists()).toBe(false)
  })

  it('edits a relative value as days from today', async () => {
    const w = mount(RelativeDateFilter, { props: { modelValue: 'today-30' }, slots, global })
    const days = w.find('input[type="number"]')
    expect((days.element as HTMLInputElement).value).toBe('-30')
    expect(w.find('[data-test="picker"]').exists()).toBe(false)
    await days.setValue('7')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['today+7'])
  })

  it('follows a fixed date set from outside, keeps the mode for an empty value', async () => {
    const w = mount(RelativeDateFilter, { props: { modelValue: 'today-30' }, slots, global })
    await w.setProps({ modelValue: '' })
    expect(w.find('input[type="number"]').exists()).toBe(true)
    await w.setProps({ modelValue: '2026-01-15' })
    expect(w.find('[data-test="picker"]').exists()).toBe(true)
    expect(w.find('input[type="number"]').exists()).toBe(false)
  })
})
