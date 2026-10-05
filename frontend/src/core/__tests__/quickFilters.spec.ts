import { describe, expect, it } from 'vitest'
import { buildQuickFilterForField } from '@/core/quickFilters'
import type { DocField } from '@/types'

const dateField = (extra: Partial<DocField> = {}): DocField =>
  ({ fieldname: 'signed_on', label: 'Signed on', fieldtype: 'Date', in_quick_filter: true, ...extra }) as DocField

describe('buildQuickFilterForField', () => {
  it('Date field defaults to an exact-date picker', () => {
    const ff = buildQuickFilterForField(dateField())
    expect(ff.input_type).toBe('date')
    expect(ff.operator).toBe('eq')
  })

  it("quick_filter_mode 'year' picks a calendar year", () => {
    const ff = buildQuickFilterForField(dateField({ quick_filter_mode: 'year' }))
    expect(ff.input_type).toBe('year')
    expect(ff.operator).toBe('year')
    expect(ff.on_change.debounce_ms).toBe(0)
  })

  it('year mode applies to Datetime but not to other field types', () => {
    expect(buildQuickFilterForField(dateField({ fieldtype: 'Datetime', quick_filter_mode: 'year' })).operator).toBe('year')
    expect(buildQuickFilterForField(dateField({ fieldtype: 'Int', quick_filter_mode: 'year' })).operator).toBe('eq')
  })
})
