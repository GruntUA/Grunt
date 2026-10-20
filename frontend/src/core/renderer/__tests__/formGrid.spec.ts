import { describe, expect, it } from 'vitest'
import type { DocField } from '@/types'
import { columnWidths, flattenLayout, parseLayout } from '@/core/composables/useFormLayout'
import { columnTemplate, fieldSpanClass, hasFieldWidths, sectionGridClass, twelfths } from '../formGrid'

const f = (fieldname: string, fieldtype = 'Data', extra: Partial<DocField> = {}) =>
  ({ fieldname, label: fieldname, fieldtype, ...extra }) as DocField

describe('form widths (`columns`, twelfths)', () => {
  it('reads anything outside 1-12 as full width', () => {
    expect([twelfths(6), twelfths('4'), twelfths(0), twelfths(13), twelfths(undefined)]).toEqual([6, 4, 12, 12, 12])
  })

  it('equal columns need no template; set widths share the rest', () => {
    expect(columnTemplate([12, 12], 2)).toBeNull()
    expect(columnTemplate([8, 4], 2)).toBe('minmax(0, 8fr) minmax(0, 4fr)')
    expect(columnTemplate([6, 12, 12], 3)).toBe('minmax(0, 6fr) minmax(0, 3fr) minmax(0, 3fr)')
    expect(sectionGridClass([12, 12], 2)).toBe('@lg:grid-cols-2')
    expect(sectionGridClass([8, 4], 2)).toBe('@lg:grid-cols-(--form-cols)')
  })

  it('fields narrower than the column span part of a 12-grid', () => {
    expect(hasFieldWidths([f('a'), f('b')])).toBe(false)
    expect(hasFieldWidths([f('a', 'Data', { columns: 6 }), f('b')])).toBe(true)
    expect(fieldSpanClass(f('a', 'Data', { columns: 4 }))).toBe('col-span-12 @sm:col-span-4')
  })
})

describe('Column fields in the layout', () => {
  const fields = [
    f('sec', 'Section'),
    f('col_a', 'Column', { columns: 8 }),
    f('a'),
    f('col_b', 'Column', { columns: 4, label: 'Side' }),
    f('b'),
  ]

  it('a leading Column describes the first column, the next one starts the second', () => {
    const [section] = parseLayout(fields)[0].sections
    expect(section.columns.map((c) => c.map((x) => x.fieldname))).toEqual([['a'], ['b']])
    expect(section._columnFieldnames).toEqual(['col_b'])
    expect(columnWidths(section)).toEqual([8, 4])
  })

  it('round-trips without losing Column properties', () => {
    expect(flattenLayout(parseLayout(fields))).toEqual(fields)
  })
})
