import { describe, it, expect, vi } from 'vitest'
import { hasTrait, isDateType, isNumericType } from '@/core/fieldRegistry'

// The discovered ListCell / FilterInput components drag in stores that need a
// real browser - stand them in with stubs, the registries only key them by type.
vi.mock('@/core/composables/useColorMode', () => ({ useColorMode: () => ({}) }))

describe('field traits (synced from the backend FieldType)', () => {
  it('reads traits from manifest.json', () => {
    expect(hasTrait('Link', 'link')).toBe(true)
    expect(hasTrait('DynamicLink', 'link')).toBe(false)
    expect(hasTrait('Table', 'table')).toBe(true)
    expect(hasTrait('Image', 'file')).toBe(true)
    expect(hasTrait('Password', 'sensitive')).toBe(true)
    expect(hasTrait('MultiSelect', 'options')).toBe(true)
    expect(hasTrait('Unknown', 'link')).toBe(false)
  })

  it('derives numeric / date from storage_class', () => {
    for (const t of ['Int', 'Float', 'Currency', 'Percent', 'Duration', 'Rating']) expect(isNumericType(t)).toBe(true)
    for (const t of ['Data', 'Check', 'Date']) expect(isNumericType(t)).toBe(false)
    expect(isDateType('Date')).toBe(true)
    expect(isDateType('Datetime')).toBe(true)
    expect(isDateType('Time')).toBe(false)
  })
})

describe('filter / list-cell registries', async () => {
  const { getFilterConfig, registerFilterConfig } = await import('@/core/filterRegistry')
  const { getListCell } = await import('@/core/listCellRegistry')
  const DefaultListCell = (await import('@/components/fields/Default/ListCell.vue')).default
  const DefaultFilterInput = (await import('@/components/fields/Default/FilterInput.vue')).default

  it('derives operators from the field type', () => {
    expect(getFilterConfig('Percent').operators).toContain('>=')
    expect(getFilterConfig('Date').operators).toContain('<')
    expect(getFilterConfig('Check').operators).toEqual(['='])
    expect(getFilterConfig('Select').operators).not.toContain('like')
    expect(getFilterConfig('Link').operators).toContain('child_of')
    expect(getFilterConfig('MultiSelect').operators).toContain('like')
    expect(getFilterConfig('SomePluginType').operators).toContain('like')
  })

  it('discovers FilterInput.vue / ListCell.vue by folder name', () => {
    expect(getFilterConfig('Link').filterInput).not.toBe(DefaultFilterInput)
    expect(getFilterConfig('Data').filterInput).toBe(DefaultFilterInput)
    expect(getListCell('MultiSelect')).not.toBe(DefaultListCell)
    expect(getListCell('Data')).toBe(DefaultListCell)
  })

  it('lets an explicit registration override the derived config', () => {
    registerFilterConfig('Percent', { operators: ['='] })
    expect(getFilterConfig('Percent').operators).toEqual(['='])
    expect(getFilterConfig('Percent').filterInput).toBe(DefaultFilterInput)
  })
})
