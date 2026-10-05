import { describe, it, expect, beforeEach } from 'vitest'
import { useListColumns } from '@/core/composables/useListColumns'
import type { DocField } from '@/types'

// Fixtures

function makeField(overrides: Partial<DocField>): DocField {
  return {
    fieldname: 'test_field',
    label: 'Test Field',
    fieldtype: 'Text',
    required: false,
    ...overrides,
  }
}

const titleField = makeField({ fieldname: 'title', label: 'Title', fieldtype: 'Text', in_list_view: true })
const statusField = makeField({ fieldname: 'status', label: 'Status', fieldtype: 'Select', in_list_view: true })
const hiddenField = makeField({ fieldname: 'secret', label: 'Secret', fieldtype: 'Text', hidden: true })
const sectionField = makeField({ fieldname: 'section_1', label: 'Section', fieldtype: 'Section' })
const tableField = makeField({ fieldname: 'items', label: 'Items', fieldtype: 'Table' })
const extraField = makeField({ fieldname: 'notes', label: 'Notes', fieldtype: 'LongText', in_list_view: false })

describe('useListColumns', () => {
  const doctype = `TestDocType_${Math.random()}`

  beforeEach(() => {
    // Clear any saved column preferences to ensure test isolation
    const key = `grunt_columns_v2_${doctype}`
    localStorage.removeItem(key)
  })

  describe('allAvailableColumns', () => {
    it('includes non-structural, non-hidden fields', () => {
      const { allAvailableColumns } = useListColumns(doctype, () => [titleField, statusField])
      expect(allAvailableColumns.value.map(c => c.key)).toEqual(['title', 'status'])
    })

    it('excludes hidden fields', () => {
      const { allAvailableColumns } = useListColumns(doctype, () => [titleField, hiddenField])
      expect(allAvailableColumns.value.map(c => c.key)).not.toContain('secret')
    })

    it('excludes structural field types', () => {
      const { allAvailableColumns } = useListColumns(doctype, () => [titleField, sectionField, tableField])
      const keys = allAvailableColumns.value.map(c => c.key)
      expect(keys).not.toContain('section_1')
      expect(keys).not.toContain('items')
    })

    it('maps label correctly', () => {
      const { allAvailableColumns } = useListColumns(doctype, () => [titleField])
      expect(allAvailableColumns.value[0].label).toBe('Title')
    })
  })

  describe('default visible columns', () => {
    it('shows only in_list_view fields by default', () => {
      const { visibleColumns } = useListColumns(doctype, () => [titleField, statusField, extraField])
      const keys = visibleColumns.value.map(c => c.key)
      expect(keys).toContain('title')
      expect(keys).toContain('status')
      expect(keys).not.toContain('notes')
    })

    it('falls back to ["name"] when no in_list_view fields', () => {
      const { visibleKeys } = useListColumns(doctype, () => [extraField])
      expect(visibleKeys.value).toEqual(['name'])
    })
  })

  describe('isVisible', () => {
    it('returns true for a default visible field', () => {
      const { isVisible } = useListColumns(doctype, () => [titleField])
      expect(isVisible('title')).toBe(true)
    })

    it('returns false for a non-visible field', () => {
      const { isVisible } = useListColumns(doctype, () => [titleField, extraField])
      expect(isVisible('notes')).toBe(false)
    })
  })

  describe('toggleCol', () => {
    it('adds a hidden column to visible set', () => {
      const { isVisible, toggleCol } = useListColumns(doctype, () => [titleField, extraField])
      expect(isVisible('notes')).toBe(false)
      toggleCol('notes')
      expect(isVisible('notes')).toBe(true)
    })

    it('removes a visible column from visible set', () => {
      const { isVisible, toggleCol } = useListColumns(doctype, () => [titleField, statusField])
      expect(isVisible('status')).toBe(true)
      toggleCol('status')
      expect(isVisible('status')).toBe(false)
    })

    it('persists preference to localStorage', () => {
      const key = `grunt_columns_v2_${doctype}`
      const { toggleCol } = useListColumns(doctype, () => [titleField, extraField])
      toggleCol('notes')
      const stored = JSON.parse(localStorage.getItem(key)!)
      expect(stored).toContain('notes')
    })

    it('restores saved preferences on re-instantiation', () => {
      const { toggleCol } = useListColumns(doctype, () => [titleField, extraField])
      toggleCol('notes')
      // Re-create composable instance (simulates page reload)
      const { isVisible } = useListColumns(doctype, () => [titleField, extraField])
      expect(isVisible('notes')).toBe(true)
    })
  })
})
