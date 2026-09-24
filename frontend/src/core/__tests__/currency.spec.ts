import { describe, it, expect, beforeEach } from 'vitest'
import { siteConfigState } from '@/core/composables/useSiteConfig'
import { currencyCode, currencySymbol, formatCurrency } from '@/core/currency'
import type { DocField } from '@/types'

const field = (options?: string) => ({ fieldname: 'amount', fieldtype: 'Currency', label: 'Amount', options }) as DocField

beforeEach(() => {
  Object.assign(siteConfigState(), { language: 'uk-UA' })
})

describe('core/currency', () => {
  it('resolves the code from a sibling field, else a fixed ISO code', () => {
    expect(currencyCode(field('currency'), { currency: 'EUR' })).toBe('EUR')
    expect(currencyCode(field('currency'), { currency: null })).toBeNull()
    expect(currencyCode(field('UAH'))).toBe('UAH')
    expect(currencyCode(field('currency'))).toBeNull()
    expect(currencyCode(field())).toBeNull()
  })

  it('formats with two decimals and the currency symbol', () => {
    const s = formatCurrency(12345.6, 'UAH').replace(/\s/g, ' ')
    expect(s).toBe('12 345,60 ₴')
    expect(formatCurrency(1.5, null)).toBe('1,50')
    expect(formatCurrency(null, 'UAH')).toBe('')
  })

  it('falls back to plain number / code for unknown currencies', () => {
    expect(formatCurrency(2, 'XX1')).toBe('2,00')
    expect(currencySymbol('UAH')).toBe('₴')
    expect(currencySymbol(null)).toBe('')
  })
})
