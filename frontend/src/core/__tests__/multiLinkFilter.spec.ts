import { describe, expect, it, vi } from 'vitest'
import { isFilterableType } from '@/core/fieldRegistry'
import { getFilterConfig } from '@/core/filterRegistry'
import { buildQuickFiltersFromFields } from '@/core/quickFilters'
import type { DocField } from '@/types'

vi.hoisted(() => {
  // jsdom lacks matchMedia; the filter inputs' import chain reads it on load.
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
})

describe('MultiLink filters', () => {
  it('is filterable despite having no column, unlike Table', () => {
    expect(isFilterableType('MultiLink')).toBe(true)
    expect(isFilterableType('Table')).toBe(false)
    expect(isFilterableType('Data')).toBe(true)
  })

  it('offers the junction-table operators, without child_of', () => {
    const ops = getFilterConfig('MultiLink').operators
    expect(ops).toEqual(['=', '!=', 'in', 'not in', 'is set', 'is not set'])
    expect(getFilterConfig('Link').operators).toContain('child_of')
  })

  it('becomes a link quick filter', () => {
    const field = { fieldname: 'tags', label: 'Tags', fieldtype: 'MultiLink', options: 'Tag', in_quick_filter: true } as DocField
    const [ff] = buildQuickFiltersFromFields([field])
    expect(ff).toMatchObject({ field: 'tags', input_type: 'link', operator: 'eq' })
  })
})
