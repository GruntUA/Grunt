import { describe, expect, it } from 'vitest'
import { buildQuickFilterForField, buildQuickFiltersFromFields, withAsOfDateFilter } from '@/core/quickFilters'
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

describe('withAsOfDateFilter', () => {
  const validFrom = dateField({ fieldname: 'valid_from', label: 'Valid from' })

  it('leaves filters alone without an as-of field', () => {
    const filters = [buildQuickFilterForField(dateField())]
    expect(withAsOfDateFilter(filters, { fields: [dateField()] }, 'As of')).toBe(filters)
  })

  it('appends a tree-only as_of_date filter when none covers the field', () => {
    const [ff] = withAsOfDateFilter([], { fields: [validFrom] }, 'As of')
    expect(ff).toMatchObject({ id: 'as_of_date', field: 'valid_from', operator: 'lte_or_null', enabled_in: ['tree'] })
  })

  it('converts an existing quick filter on that field and enables it in the tree', () => {
    const qf = { ...buildQuickFilterForField(validFrom), enabled_in: ['list'] as Array<'list' | 'tree'> }
    const result = withAsOfDateFilter([qf], { fields: [validFrom] }, 'As of')
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ id: 'as_of_date', operator: 'lte_or_null', label: 'Valid from', enabled_in: ['list', 'tree'] })
  })

  it('prefers tree_as_of_date_field over valid_from', () => {
    const [ff] = withAsOfDateFilter([], { fields: [validFrom, dateField()], tree_as_of_date_field: 'signed_on' }, 'As of')
    expect(ff.field).toBe('signed_on')
  })
})

describe('quick_filter from the field manifest', () => {
  const field = (fieldtype: string) => dateField({ fieldname: 'f', fieldtype })

  it('maps the manifest input type and picks the operator', () => {
    expect(buildQuickFilterForField(field('Data'))).toMatchObject({ input_type: 'text', operator: 'ilike' })
    expect(buildQuickFilterForField(field('Time'))).toMatchObject({ input_type: 'text', operator: 'eq' })
    expect(buildQuickFilterForField(field('Currency'))).toMatchObject({ input_type: 'number', operator: 'eq' })
    expect(buildQuickFilterForField(field('Link'))).toMatchObject({ input_type: 'link', operator: 'eq' })
  })

  it('skips types without quick_filter', () => {
    const fields = ['Data', 'Table', 'Percent'].map(t => ({ ...field(t), fieldname: t }))
    expect(buildQuickFiltersFromFields(fields).map(ff => ff.field)).toEqual(['Data'])
  })
})
