import { describe, it, expect } from 'vitest'
import { EMPTY_VALUE, formatValue, registerFormatter } from '@/core/formatValue'
import { buildPopupTableHtml } from '@/core/map/popupFormatter'
import type { DocField } from '@/types'

describe('formatValue', () => {
  it('shows a dash for empty values', () => {
    for (const v of [null, undefined, '']) expect(formatValue({ fieldtype: 'Data' }, v)).toBe(EMPTY_VALUE)
  })

  it('uses the type\'s own format.ts', () => {
    expect(formatValue({ fieldtype: 'Check' }, 1)).toBe('✓')
    expect(formatValue({ fieldtype: 'Check' }, '0')).toBe('✗')
    expect(formatValue({ fieldtype: 'Rating' }, 3.5)).toBe('★★★½☆ 3.5')
    expect(formatValue({ fieldtype: 'Rating' }, 17)).toBe('17') // e.g. a report total
    expect(formatValue({ fieldtype: 'Geolocation' }, { lat: 50.4501, lng: 30.5234 })).toBe('50.45010, 30.52340')
  })

  it('falls back to locale numbers, JSON and strings', () => {
    expect(formatValue({ fieldtype: 'Int' }, 1234567)).toMatch(/^1\D?234\D?567$/)
    expect(formatValue({ fieldtype: 'JSON' }, { a: 1 })).toBe('{"a":1}')
    expect(formatValue({ fieldtype: 'Data' }, 'abc')).toBe('abc')
  })

  it('lets a plugin register a formatter', () => {
    registerFormatter('PluginType', (v) => `#${v}`)
    expect(formatValue({ fieldtype: 'PluginType' }, 7)).toBe('#7')
  })
})

describe('buildPopupTableHtml', () => {
  it('escapes labels and values', () => {
    const fields = [{ fieldname: 'note', label: '<b>Note</b>', fieldtype: 'Data' }] as DocField[]
    const html = buildPopupTableHtml({ note: '<img src=x onerror=alert(1)>' }, fields, 'title')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<b>')
    expect(html).toContain('&lt;img')
  })
})
